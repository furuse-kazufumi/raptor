#!/usr/bin/env zx

/**
 * RAPTOR セッション自動ローテーター
 *
 * 使い方:
 *   ccr                                        # D:\projects\ を自動スキャンしてメニュー表示
 *   ccr --project D:\projects\llmesh           # 直接指定
 *   ccr --no-project                           # プロジェクト指定なし
 *
 * プロジェクト管理:
 *   D:\projects\ 以下のディレクトリを自動検出。
 *   claude-projects.json で名前・説明を上書き可能（任意）。
 *
 * ファイル規則（全プロジェクト共通、docs/ 以下）:
 *   SESSION_SUMMARY.md  → セッション引き継ぎ（/rotate が書く）
 *   PROGRESS.md         → 実装進捗
 *   DEBUG_LOG.md        → デバッグ記録
 *   TEST_RESULTS.md     → テスト結果
 *   REQUIREMENTS.md     → 要件定義
 *   ROADMAP.md          → ロードマップ
 *
 * シグナル規則:
 *   .rotate-signal       → ローテーション要求（Claude が RAPTOR dir に作成）
 *   .raptor-session.json → 現在のプロジェクト情報（ラッパーが起動時に書く）
 *
 * 起動時コマンド投入 (シーケンシャル):
 *   node-pty で Claude Code を擬似端末上に起動し、`/effort ultracode` 等の
 *   初期コマンド列を 1 件ずつ submit してから対話を実端末へ引き渡す。
 *   注意 (2026-05-31 連結バグ "再々発" で判明): スラッシュコマンドを打つと TUI の
 *   オートコンプリートメニューが開き、その状態の Enter(\r) は「送信」でなく
 *   「メニュー確定」として吸収され送信されない。さらに /effort のように引数候補
 *   (low/medium/.../ultracode) を持つコマンドは引数メニューも開く。旧対策の
 *   「Enter を 2 回送る」は、2 回目の Enter がメニュー吸収後に「改行挿入」となって
 *   入力欄を複数行化させ、行単位クリア(Ctrl+U)では消えない残骸を残し、次コマンド
 *   本文が `/effort ultracode\n<本文>` と連結→ Invalid argument で停止していた
 *   (= 旧対策自体が連結を誘発)。
 *   現対策: (1) 各コマンド前に Esc×2 (メニュー閉→テキスト全クリア) + Ctrl+U で
 *   入力欄を確実に空にする (複数行残骸も除去)。(2) スラッシュコマンドは本文投入後
 *   Enter の前に Esc を 1 回送り引数メニューだけ閉じてから、Enter は 1 回だけ送る。
 *   万一その Esc がテキストごと消しても続く Enter は空欄 no-op で連結せず、最悪
 *   effort 不適用で済む (フリーズしない)。A/B 切り分けは RAPTOR_AUTO_SLASH_DOUBLE_ENTER=1。
 *   なお投入の各待ち (起動 / キー間 / submission 間) は既定で固定 sleep ではなく PTY
 *   出力の静止検知 (quiescence gating, waitQuiet) で行い *_MAX_MS でハードキャップする。
 *   RAPTOR_AUTO_QUIESCE_DISABLE=1 で旧固定 sleep に退避。
 *   詳細仕様: docs/CCR_AUTO_RESTART.md
 */

import { createInterface } from 'readline';
import { createRequire } from 'module';
import { fileURLToPath } from 'url';

// node-pty (prebuilt fork) をスクリプト基準で解決する。zx の require ではなく
// createRequire を使い、raptor/node_modules を確実に参照させる。
const nodeRequire = createRequire(import.meta.url);

// SCRIPT_DIR は「claude-auto.mjs 自身のあるディレクトリ」を指す必要がある。
// 旧実装 path.dirname(process.argv[1]) は zx 経由起動 (`zx claude-auto.mjs`) だと
// argv[1] が zx の CLI 本体 (…/zx/build/cli.js) になり、SCRIPT_DIR が zx の build
// ディレクトリを指してしまう (2026-05-31 判明)。その結果 .raptor-session.json /
// .input-debug.log / claude-projects.json / .rotate-signal が node_modules 配下に
// 読み書きされ、CLAUDE.md SESSION START が cwd 側の古いファイルを読む・/rotate の
// signal 監視が空振りする等の silent 障害を起こしていた。import.meta.url から解決すれば
// 起動経路 (zx / 直接 node / シンボリックリンク) に依らず常に正しい自分の場所を得る。
const SCRIPT_DIR    = path.dirname(fileURLToPath(import.meta.url));
// On Windows use PowerShell so claude.exe is found via PATH
if (process.platform === 'win32') {
  $.shell = 'pwsh.exe';
  $.prefix = '';
}

const CLAUDE_EXE = (() => {
  // テスト用オーバーライド: モック実行ファイルを spawn して launcher 全体 (selectProject →
  // runClaudeWithPty → submitSequence の quiescence gating) を E2E 検証するための逃げ道。
  // 未設定なら従来どおり (既定挙動は不変)。RAPTOR_AUTO_CLAUDE_ARGS と併用。
  if (process.env.RAPTOR_AUTO_CLAUDE_EXE) return process.env.RAPTOR_AUTO_CLAUDE_EXE;
  if (process.platform === 'win32') {
    const home = process.env.USERPROFILE || process.env.HOME || '';
    const candidate = path.join(home, '.local', 'bin', 'claude.exe');
    return fs.existsSync(candidate) ? candidate : 'claude';
  }
  return process.env.HOME ? `${process.env.HOME}/.local/bin/claude` : 'claude';
})();
const SIGNAL_FILE   = path.join(SCRIPT_DIR, '.rotate-signal');
const SESSION_CFG   = path.join(SCRIPT_DIR, '.raptor-session.json');
const PROJECTS_DIR  = String.raw`D:\projects`;
const METADATA_CFG  = path.join(SCRIPT_DIR, 'claude-projects.json');

// ─── 端末「リッチ入力」モードのリセット ───────────────────────
// TUI (Claude Code 等) が有効化する rich-input モードを無効化する制御列。
// これらは端末エミュレータ側の状態 (DECSET) で、node プロセスが死んでも端末に残る。
// 特に win32-input-mode (?9001) は ConPTY が有効化し、キー入力を
//   CSI Vk;Sc;Uc;Kd;Cs;Rc _   形式のレコードへ符号化する。これが残存すると
// 次回 ccr の selectProject() の readline が cooked 行入力を受け取れず、Enter を
// 認識できないまま生バイトをエコーして「番号を選択 [4]: ;13;1;0;1_…」と化ける
// (2026-05-31 の ptyProc.kill()/process.exit(0) 急停止で ConPTY が終了時に
//  無効化シーケンスを出せず端末に残るのが原因)。
const TERM_INPUT_RESET =
  '\x1b[?9001l' +                                   // win32-input-mode off (ConPTY rich input)
  '\x1b[?2004l' +                                   // bracketed paste off
  '\x1b[?1000l\x1b[?1002l\x1b[?1003l\x1b[?1006l' +  // mouse tracking off
  '\x1b[<u';                                        // kitty keyboard protocol を 1 段 pop (無ければ no-op)

// 制御列を実端末へ書く。stderr 優先 (メニュー出力と同じ宛先)、無ければ stdout。
function resetTerminalInput() {
  try {
    const s = process.stderr.isTTY ? process.stderr : process.stdout;
    if (s && s.isTTY) s.write(TERM_INPUT_RESET);
  } catch {}
}

// docs/ 標準ファイルパスを返す
function projectDocs(projectPath) {
  const base = projectPath ?? SCRIPT_DIR;
  return {
    dir:      path.join(base, 'docs'),
    summary:  path.join(base, 'docs', 'SESSION_SUMMARY.md'),
    progress: path.join(base, 'docs', 'PROGRESS.md'),
    debug:    path.join(base, 'docs', 'DEBUG_LOG.md'),
    tests:    path.join(base, 'docs', 'TEST_RESULTS.md'),
  };
}

// ─── D:\projects\ を自動スキャン ─────────────────────────────
async function discoverProjects() {
  // メタデータ上書き（任意）: { "llmesh": { name, description }, ... }
  let meta = {};
  try { meta = await fs.readJson(METADATA_CFG); } catch {}

  let entries = [];
  try {
    entries = await fs.readdir(PROJECTS_DIR, { withFileTypes: true });
  } catch {
    console.error(chalk.red(`[ERROR] ${PROJECTS_DIR} を読み込めません`));
    return [];
  }

  return entries
    .filter(e => e.isDirectory())
    .map(e => {
      const key  = e.name.toLowerCase();
      const pMeta = meta[e.name] ?? meta[key] ?? {};
      return {
        name:        pMeta.name        ?? e.name,
        path:        path.join(PROJECTS_DIR, e.name),
        description: pMeta.description ?? '',
      };
    })
    .sort((a, b) => a.name.localeCompare(b.name, 'ja'));
}

// ─── SESSION_SUMMARY.md の更新時刻を返す (存在しなければ 0) ──
function summaryMtime(projectPath) {
  try {
    const s = fs.statSync(path.join(projectPath, 'docs', 'SESSION_SUMMARY.md'));
    return s.mtimeMs;
  } catch {
    return 0;
  }
}

// 経過時間を人間が読める形式に変換
function relTime(ms) {
  if (ms === 0) return '';
  const sec  = Math.round((Date.now() - ms) / 1000);
  if (sec < 60)   return `${sec}秒前`;
  const min  = Math.round(sec / 60);
  if (min < 60)   return `${min}分前`;
  const hr   = Math.round(min / 60);
  if (hr < 24)    return `${hr}時間前`;
  return `${Math.round(hr / 24)}日前`;
}

// 環境変数の数値パース: 未設定/空文字は既定へ、NaN/負/非数値も既定へフォールバックする。
// 特に quiescence gating の maxMs が NaN だとハードキャップ (now-start >= maxMs) が
// 恒偽になりキャップが無効化され waitQuiet が回り続けうる (review 2026-06-01 low#1/#2)。
// 旧固定 sleep 経路でも zx の sleep(NaN) は throw するため、全数値 knob はこれを通す。
const envNum = (v, d) => {
  if (v === undefined || v === '') return d;
  const n = Number(v);
  return Number.isFinite(n) && n >= 0 ? n : d;
};

// ─── プロジェクト選択 ─────────────────────────────────────────
async function selectProject() {
  if (argv.project && argv.project !== true) return String(argv.project);
  if (argv['no-project']) return null;

  const projects = await discoverProjects();

  // 各プロジェクトの SESSION_SUMMARY.md 更新時刻を付加
  const enriched = projects.map(p => ({
    ...p,
    mtime: summaryMtime(p.path),
  }));

  // 最近作業したプロジェクト（mtime 最大）をデフォルトにする
  let defaultNum = 0;
  let maxMtime = 0;
  enriched.forEach((p, i) => {
    if (p.mtime > maxMtime) { maxMtime = p.mtime; defaultNum = i + 1; }
  });

  // 前回 ccr/Claude セッションが端末に残した win32-input-mode 等を無効化してから
  // readline で cooked 行入力を取る (これが無いと Enter が認識されず化ける)。
  resetTerminalInput();
  // 端末が DECRST (?9001l 等) を解釈する猶予を与えてから readline を作る。
  // これが無いと reset→readline が同一同期 tick で走り、Windows Terminal が
  // win32-input-mode を無効化する前に最初のキーが win32 符号化されて化けうる
  // (workflow 検証 high finding 2026-05-31)。RAPTOR_AUTO_RESET_GRACE_MS で調整可。
  await sleep(Number(process.env.RAPTOR_AUTO_RESET_GRACE_MS || 60));

  // DEBUG: メニュー入力の生バイトを記録 (win32-input-mode 化けの証拠取得用)。
  // onInput (PTY 経路) は claude 起動後の入力しか記録しないため、化けが起きる
  // selectProject の readline はこの tap が無いと .input-debug.log に残らない。
  const inputDebug = process.env.RAPTOR_AUTO_INPUT_DEBUG === '1';
  let menuTap = null;
  if (inputDebug) {
    const dbgPath = path.join(SCRIPT_DIR, '.input-debug.log');
    menuTap = d => {
      try { fs.appendFileSync(dbgPath, `${new Date().toISOString()} [selectProject] ${Buffer.from(d).toString('hex')}\n`); } catch {}
    };
    try { process.stdin.on('data', menuTap); } catch {}
  }

  console.error(chalk.bold.cyan('\n╔══ RAPTOR プロジェクト選択 ══╗'));
  if (enriched.length === 0) {
    console.error(chalk.gray(`  (${PROJECTS_DIR} にプロジェクトが見つかりません)`));
  }
  enriched.forEach((p, i) => {
    const num      = i + 1;
    const isDefault = num === defaultNum;
    const rel      = relTime(p.mtime);
    const resumeTag = p.mtime > 0
      ? chalk.yellow(` [resume ${rel}]`)
      : '';
    const desc     = p.description ? chalk.gray(` — ${p.description}`) : '';
    const marker   = isDefault ? chalk.green('▶') : ' ';
    const numStr   = chalk.yellow(String(num).padStart(2));
    console.error(`  ${marker}${numStr}. ${chalk.white(p.name)}${desc}${resumeTag}`);
  });
  console.error(`   ${chalk.yellow('0')}. プロジェクト指定なし`);
  console.error(chalk.bold.cyan('╚════════════════════════════╝\n'));

  const prompt = defaultNum > 0
    ? `番号を選択 [${defaultNum}]: `
    : '番号を選択 [0]: ';

  const rl = createInterface({ input: process.stdin, output: process.stderr });
  // 60 秒無入力で既定 (最新プロジェクト) を自動選択。無人連続処理を止めないため。
  const AUTO_SELECT_MS = 60_000;
  const answer = await new Promise(resolve => {
    const timer = setTimeout(() => {
      const dflt = defaultNum > 0 ? enriched[defaultNum - 1]?.name ?? '既定' : 'プロジェクト指定なし';
      console.error(chalk.yellow(`\n  [AUTO] ${AUTO_SELECT_MS / 1000}秒無入力 → 既定を自動選択: ${dflt}`));
      rl.close();
      resolve('');  // 空 → defaultNum にマップ
    }, AUTO_SELECT_MS);
    rl.question(prompt, ans => { clearTimeout(timer); rl.close(); resolve(ans.trim()); });
  });

  if (menuTap) { try { process.stdin.removeListener('data', menuTap); } catch {} }

  const num = answer === '' ? defaultNum : (parseInt(answer) || 0);
  if (num < 1 || num > enriched.length) return null;
  const chosen = enriched[num - 1];
  console.error(chalk.green(`  → ${chosen.name} (${chosen.path})\n`));
  return chosen.path;
}

// ─── セッション設定ファイルを書く ─────────────────────────────
async function writeSessionConfig(projectPath, projects) {
  const project = projects?.find(p => p.path === projectPath);
  const docs = projectDocs(projectPath);
  const config = {
    projectName:  project?.name ?? (projectPath ? path.basename(projectPath) : 'default'),
    projectPath:  projectPath ?? SCRIPT_DIR,
    docsDir:      docs.dir,
    summaryFile:  docs.summary,
    progressFile: docs.progress,
    debugFile:    docs.debug,
    testFile:     docs.tests,
  };
  // 同期書き込みで silent fail を防ぐ。失敗時はユーザーに見える形で警告する。
  try {
    const fsSync = await import('fs');
    fsSync.writeFileSync(SESSION_CFG, JSON.stringify(config, null, 2), 'utf-8');
    console.error(chalk.gray(`  [SESSION] .raptor-session.json 書き込み: ${config.projectName}`));
  } catch (e) {
    console.error(chalk.red(`  [SESSION] .raptor-session.json 書き込み失敗: ${e.message}`));
    console.error(chalk.red(`            CLAUDE.md SESSION START の自動継続が機能しません。`));
  }
}

// ─── 初期コマンド列を組み立てる ───────────────────────────────
// 各要素は「1 つの submission」として順番に投入される (連結しない)。
// 順序: /effort <level> → (任意 preCommands) → 再開トリガー (1 行)。
//
// 設計方針 (2026-05-31 ユーザー指示「ultracode で動くようにだけして、復元は
// CLAUDE.md に参照先パスだけ書けばよい」): ccr 側の責務は「ultracode を効かせる」+
// 「自律継続の合図を送る」までに絞る。前回作業の復元手順・参照先パス
//   (.raptor-session.json / RAPTOR_CALLER_DIR / claude-projects.json の plan_ref /
//    各プロジェクト docs/SESSION_SUMMARY.md / feedback_max_plan_autonomy)
// は CLAUDE.md の SESSION START 節が唯一の正本として保持する。よって再開トリガーは
// 旧来の長い復元プロンプト (確認するな・選択肢を出すな等) ではなく
// 「SESSION START に従って自律継続せよ」の 1 行だけにし、文言重複と連結リスクを減らす。
//   env: RAPTOR_AUTO_EFFORT_LEVEL='' で effort 無効化
//      / RAPTOR_AUTO_RESUME_PROMPT で再開トリガーを上書き ('' で無効化 = effort のみ)
//      / RAPTOR_AUTO_PRECOMMANDS は '||' 区切りで /effort と再開トリガーの間に追加投入。
function buildInitialCommands(hasSummary) {
  const cmds = [];
  const effort = process.env.RAPTOR_AUTO_EFFORT_LEVEL ?? 'ultracode';
  if (effort) cmds.push(`/effort ${effort}`);

  const extra = process.env.RAPTOR_AUTO_PRECOMMANDS;
  if (extra) {
    for (const c of String(extra).split('||')) {
      if (c && c.trim()) cmds.push(c.trim());
    }
  }

  // 再開トリガー (2 行目) は既定で投入しない (ユーザー指示 2026-06-01「2行目不要」)。
  //   根治理由: 旧実装は既定値に復元プロンプト文字列を置き、「2 行目を出さない」挙動を
  //   launcher (bin/ccr.ps1 / bin/ccr.cmd) が RAPTOR_AUTO_RESUME_PROMPT='' を
  //   claude-auto.mjs へ env 伝播することに依存させていた。だが長時間 marathon セッションが
  //   launcher 編集前から継続している / while ループの rotate 再利用 / 別 launcher 解決 等で
  //   env が届かないと既定値が復活し 2 行目が生成 → 引数メニューに吸収された単一 Enter で
  //   /effort ultracode と連結 → "Invalid argument" (2026-06-01 .input-debug.log [2/2] で実証)。
  //   既定を '' にして env 伝播に依存させない = 2 行目が構造的に生成され得ない →
  //   /effort と連結する余地そのものを消す。復元は CLAUDE.md SESSION START が唯一の正本
  //   (起動時に自動ロードされ、本セッションでも 2 行目なしで全復元が成立している)。
  //   明示的に再開トリガーが欲しい場合のみ RAPTOR_AUTO_RESUME_PROMPT に非空文字を設定する。
  const resume = process.env.RAPTOR_AUTO_RESUME_PROMPT ?? '';
  if (hasSummary && resume && resume.trim()) cmds.push(resume.trim());
  return cmds;
}

// ─── node-pty で Claude を起動し、初期コマンド列をシーケンシャル投入 ──
// 擬似端末 (PTY) 上で claude を起動 → 出力を実端末へ転送 / 実端末入力を PTY へ転送。
// TUI 準備後に initialCommands を 1 件ずつ submit してから対話をユーザーへ引き渡す。
// node-pty が使えない場合は通常 spawn にフォールバック (effort/連投なしで対話のみ)。
async function runClaudeWithPty(file, args, env, initialCommands) {
  let ptyLib = null;
  if (process.env.RAPTOR_AUTO_PTY_DISABLE !== '1') {
    try { ptyLib = nodeRequire('@homebridge/node-pty-prebuilt-multiarch'); }
    catch {
      try { ptyLib = nodeRequire('node-pty'); } catch {}
    }
  }

  // ── フォールバック: PTY 無し (effort/初期投入は適用されない) ──
  if (!ptyLib || typeof ptyLib.spawn !== 'function') {
    if (initialCommands.length) {
      console.error(chalk.red('  [PTY] node-pty 不在 → 通常 spawn にフォールバック (初期コマンド投入なし)'));
      console.error(chalk.gray('        有効化: raptor で `npm install` を実行'));
    }
    const { spawn } = await import('child_process');
    const { watch } = await import('fs');
    await new Promise((resolve) => {
      const child = spawn(file, args, { stdio: 'inherit', env, shell: false });
      const watcher = watch(SCRIPT_DIR, (_, filename) => {
        if (filename === '.rotate-signal' && fs.existsSync(SIGNAL_FILE)) {
          console.error(chalk.yellow('\n[ROTATE] .rotate-signal 検知 → Claude を終了します...'));
          watcher.close();
          child.kill('SIGTERM');
        }
      });
      child.on('close', () => { watcher.close(); resolve(); });
      child.on('error', () => { watcher.close(); resolve(); });
    });
    return;
  }

  // ── PTY 経路 ──
  const { watch } = await import('fs');
  const FIRST_DELAY_MS = envNum(process.env.RAPTOR_AUTO_PTY_FIRST_DELAY_MS, 2500); // TUI 起動待ち (quiescence 無効時)
  const TYPE_DELAY_MS  = envNum(process.env.RAPTOR_AUTO_PTY_TYPE_DELAY_MS,  350);  // テキスト反映待ち (同上)
  const SEQ_DELAY_MS   = envNum(process.env.RAPTOR_AUTO_SEQ_DELAY_MS,       1500); // submission 間隔 (同上)

  // ── quiescence gating (出力静止検知) ────────────────────────────
  // 固定 sleep はマシン速度に脆弱: 遅い PC / 初回オンボーディングが FIRST_DELAY を超えると
  // TUI 起動前に Esc/本文を撃ち effort が無音失敗する (CCR_FUNCTIONAL_CHECKLIST §2 HIGH #3)。
  // 代わりに PTY 出力が quietMs 静止するまで待つ (= TUI が描画を終えた合図)。spinner 等で
  // 出力が止まらない場合に備え maxMs でハードキャップし、決して旧固定 sleep 経路より長く
  // ハングしない。RAPTOR_AUTO_QUIESCE_DISABLE=1 で旧固定 sleep に退避 (回帰切り分け用)。
  // 全数値 knob は envNum で sanitize 済 (NaN/負は maxMs キャップ無効化=spin 源のため既定へ)。
  const QUIESCE          = process.env.RAPTOR_AUTO_QUIESCE_DISABLE !== '1';
  const QUIESCE_POLL_MS  = envNum(process.env.RAPTOR_AUTO_QUIESCE_POLL_MS,  25);   // 静止検知のポーリング解像度
  const STARTUP_MIN_MS   = envNum(process.env.RAPTOR_AUTO_STARTUP_MIN_MS,   1500); // TUI 起動の最低待ち (first-byte 前に早撃ちしない床)
  const STARTUP_QUIET_MS = envNum(process.env.RAPTOR_AUTO_STARTUP_QUIET_MS, 700);  // 初回出力を見た後この時間静止で準備完了とみなす
  const STARTUP_MAX_MS   = envNum(process.env.RAPTOR_AUTO_STARTUP_MAX_MS,   10000);// 起動待ちの上限 (これ以上は静止/出力に依らず進む)
  const KEY_MIN_MS       = envNum(process.env.RAPTOR_AUTO_KEY_MIN_MS,       80);   // キー入力後 write→redraw 開始を待つ床 (race 対策)
  const KEY_QUIET_MS     = envNum(process.env.RAPTOR_AUTO_KEY_QUIET_MS,     180);  // キー入力後の再描画静止待ち
  const KEY_MAX_MS       = envNum(process.env.RAPTOR_AUTO_KEY_MAX_MS,       1500); // 同上限
  const SEQ_MIN_MS       = envNum(process.env.RAPTOR_AUTO_SEQ_MIN_MS,       150);  // submission 間の最低待ち床 (race 対策)
  const SEQ_QUIET_MS     = envNum(process.env.RAPTOR_AUTO_SEQ_QUIET_MS,     400);  // submission 間の静止待ち
  const SEQ_MAX_MS       = envNum(process.env.RAPTOR_AUTO_SEQ_MAX_MS,       3500); // 同上限

  const cols = process.stdout.columns || 120;
  const rows = process.stdout.rows || 30;

  const ptyProc = ptyLib.spawn(file, args, {
    name: 'xterm-256color',
    cols, rows,
    cwd: process.cwd(),
    env,
  });

  // PTY → 実端末。quiescence gating 用に「最後に PTY 出力があった時刻」と
  // 「一度でも出力を見たか (sawData)」を記録する。sawData は起動時 quiescence が
  // first-byte 前に成立する早撃ち (review 2026-06-01 high) を防ぐためのガード。
  let lastDataTs = Date.now();
  let sawData = false;
  const onData = d => { lastDataTs = Date.now(); sawData = true; process.stdout.write(d); };
  ptyProc.onData(onData);

  // 実端末 → PTY (raw mode でキーを転送)
  const stdin = process.stdin;
  const wasRaw = !!stdin.isRaw;
  if (stdin.isTTY) { try { stdin.setRawMode(true); } catch {} }
  stdin.resume();

  // Enter キーの正規化 (2026-05-31 「Enter が送信されず溜まる」連結バグ対策):
  //   Claude Code TUI は Enter=CR(\r=0x0D) を「送信」、LF(\n=0x0A) を「改行挿入」
  //   として扱う。外側端末/PTY が Enter を \n や \r\n で渡すと内側 Claude は
  //   改行挿入と解釈し送信されず、行が溜まって 1 メッセージに連結する。
  //   そこで転送時に CRLF / 単独 LF を単一 CR へ畳む (Enter が元々 \r なら no-op)。
  //   bracketed paste (\x1b[200~ … \x1b[201~) 内の改行も Claude 側は CR を
  //   ペースト内改行として扱い送信しないため、この変換で複数行ペーストは壊れない。
  //   RAPTOR_AUTO_INPUT_RAW=1 で従来どおり無変換 (回帰時の切り分け用)。
  const normalizeEnter = process.env.RAPTOR_AUTO_INPUT_RAW !== '1';
  // 入力バイトの hex ダンプ (opt-in)。次回起動で Enter の実バイトを確証する用途。
  const inputDebug = process.env.RAPTOR_AUTO_INPUT_DEBUG === '1';
  const dbgPath = path.join(SCRIPT_DIR, '.input-debug.log');
  const onInput = d => {
    try {
      let s = d.toString('utf8');
      if (inputDebug) {
        try { fs.appendFileSync(dbgPath, `${new Date().toISOString()} ${Buffer.from(s, 'utf8').toString('hex')}\n`); } catch {}
      }
      if (normalizeEnter) s = s.replace(/\r\n|\n/g, '\r');
      ptyProc.write(s);
    } catch {}
  };
  stdin.on('data', onInput);

  // リサイズ追従
  const onResize = () => {
    try { ptyProc.resize(process.stdout.columns || cols, process.stdout.rows || rows); } catch {}
  };
  process.stdout.on('resize', onResize);

  // .rotate-signal 監視 → 検知で PTY を終了
  const watcher = watch(SCRIPT_DIR, (_, filename) => {
    if (filename === '.rotate-signal' && fs.existsSync(SIGNAL_FILE)) {
      console.error(chalk.yellow('\n[ROTATE] .rotate-signal 検知 → Claude を終了します...'));
      try { ptyProc.kill(); } catch {}
    }
  });

  // 初期コマンド列をシーケンシャル投入 (TUI 準備後)。
  // 各コマンドの 1 サイクル:
  //   (a) Esc(\x1b) ×2 … 1 回目で開いているオートコンプリート/ピッカーを閉じ、
  //       2 回目で (メニューが無ければ) 入力テキスト全体をクリアする。Ctrl+U の
  //       行単位クリアと違い複数行バッファの残骸も消せる (連結バグの主因対策)。
  //   (b) Ctrl+U(\x15) … 念のため行クリアも併用 (空欄保証)。
  //   (c) 本文を流し込む → 反映待ち
  //   (c2) slash のみ: Enter の前に Esc を 1 回送り、引数/コマンド名のオート
  //       コンプリートメニューだけを閉じる (入力テキストは保持)。これをしないと
  //       メニュー状態の Enter が「メニュー確定」として吸収され送信されない。
  //   (d) Enter(\r) を 1 回だけ送って submit。
  //       旧来の double-Enter は、メニュー吸収後の 2 回目が「改行挿入」となり
  //       入力欄が複数行化 → 次コマンドが連結する真因だったため既定では送らない
  //       (2026-05-31 実機 E2E で再発確認)。A/B 切り分け用に
  //       RAPTOR_AUTO_SLASH_DOUBLE_ENTER=1 で旧挙動へ退避可能。
  // この設計により、たとえ (c2) の Esc がテキストごと消す実装でも、続く Enter は
  // 空欄 no-op となり次コマンドと連結しない → 最悪 effort 不適用で済む
  // (= Invalid argument フリーズを構造的に防ぐ)。
  const slashDoubleEnter = process.env.RAPTOR_AUTO_SLASH_DOUBLE_ENTER === '1';
  // slash コマンドの Enter 自動送信 (既定 OFF)。CLAUDE.md SESSION START の 2026-06-01 決定
  // 「/effort ultracode の 1 行を投入し、最後の Enter はユーザーが手で押す」に合わせ、
  // 既定では slash の Enter を自動送信しない (引数メニューの Enter 吸収レースを構造回避)。
  // 無人 rotate 等で自動適用したい場合のみ RAPTOR_AUTO_SLASH_AUTOSUBMIT=1。
  const slashAutoSubmit = process.env.RAPTOR_AUTO_SLASH_AUTOSUBMIT === '1';
  const seqDbg = (msg) => {
    if (!inputDebug) return;
    try { fs.appendFileSync(dbgPath, `${new Date().toISOString()} [submitSequence] ${msg}\n`); } catch {}
  };
  // PTY 出力が quietMs 静止する (= TUI が描画を終えた合図) まで待つ。
  //   - minMs 未満では (静止していても) 返さない … 起動直後の momentary idle で早撃ちしない床。
  //   - maxMs 経過で必ず打ち切る … spinner / トークンストリーム等で出力が止まらなくても
  //     ハングせず進む (最悪でも固定 sleep 経路と同等の有界待ち)。
  // QUIESCE 無効時は呼ばれず、各 gate* が従来の固定 sleep にフォールバックする。
  const waitQuiet = async (quietMs, maxMs, minMs = 0, requireData = false) => {
    const start = Date.now();
    for (;;) {
      const now = Date.now();
      if (now - start >= maxMs) { seqDbg(`waitQuiet cap ${maxMs}ms (no quiescence, sawData=${sawData})`); return; }
      // requireData (起動時): 「一度も PTY 出力が無い」状態を「静止」と誤認しない。
      //   = first-byte 前の早撃ち防止。maxMs は依然ハードキャップなので、TUI が
      //   本当に無音のまま (起動失敗等) でも有界で必ず進む。
      const ready = (!requireData || sawData) && (now - lastDataTs >= quietMs);
      // minMs 床: キー入力後 write→redraw が始まる前に静止と誤判定しないための最低待ち。
      if (now - start >= minMs && ready) {
        seqDbg(`waitQuiet quiet after ${now - start}ms (sawData=${sawData})`);
        return;
      }
      await sleep(QUIESCE_POLL_MS);
    }
  };
  // gateFirst: 起動完了 = 「初回出力を見た後の静止」(requireData=true) で判定。
  // gateType/gateSeq: minMs 床で write→redraw 開始を待ってから静止を測る (race 対策)。
  const gateFirst = () => QUIESCE ? waitQuiet(STARTUP_QUIET_MS, STARTUP_MAX_MS, STARTUP_MIN_MS, true) : sleep(FIRST_DELAY_MS);
  const gateType  = () => QUIESCE ? waitQuiet(KEY_QUIET_MS, KEY_MAX_MS, KEY_MIN_MS) : sleep(TYPE_DELAY_MS);
  const gateSeq   = () => QUIESCE ? waitQuiet(SEQ_QUIET_MS, SEQ_MAX_MS, SEQ_MIN_MS) : sleep(SEQ_DELAY_MS);
  const submitSequence = async () => {
    if (!initialCommands.length) return;
    seqDbg(`quiesce=${QUIESCE} startup(min=${STARTUP_MIN_MS},quiet=${STARTUP_QUIET_MS},max=${STARTUP_MAX_MS})`);
    await gateFirst();                    // TUI 起動完了を出力静止で待つ (固定 2.5s の脆弱性を除去)
    for (let i = 0; i < initialCommands.length; i++) {
      const cmd = String(initialCommands[i]);
      const isSlash = cmd.trimStart().startsWith('/');
      console.error(chalk.gray(`  [SEQ] 投入 [${i + 1}/${initialCommands.length}]${isSlash ? ' (slash)' : ''}: ${cmd.split('\n')[0].slice(0, 60)}`));
      seqDbg(`begin [${i + 1}/${initialCommands.length}] slash=${isSlash} len=${cmd.length}`);
      try {
        ptyProc.write('\x1b');            // (a) メニューを閉じる
        await gateType();
        ptyProc.write('\x1b');            // (a) 2 回目: 入力テキスト全体をクリア (複数行残骸も)
        await gateType();
        ptyProc.write('\x15');            // (b) 行クリアも併用 (空欄保証)
        await gateType();
        ptyProc.write(cmd);               // (c) 本文投入
        await gateType();
        if (isSlash) {
          ptyProc.write('\x1b');          // (c2) slash: 引数メニューを閉じる (テキスト保持)
          await gateType();
        }
        // (d) 送信。非 slash はそのまま単一 Enter で送る。
        //   slash は既定で Enter を自動送信せず、本文をボックスに残してユーザーの手 Enter に
        //   委ねる (CLAUDE.md SESSION START 2026-06-01 決定「最後の Enter はユーザーが手で押す」)。
        //   これで (1) 自動 Enter が引数メニュー確定に吸われ次行と連結する race と、
        //   (2) Esc がテキストごと消す TUI 実装での ultracode 無音 drop の両方を構造的に回避する。
        //   無人 rotate 等で自動適用したい場合のみ RAPTOR_AUTO_SLASH_AUTOSUBMIT=1 (+ 旧 double は
        //   RAPTOR_AUTO_SLASH_DOUBLE_ENTER=1)。
        if (!isSlash || slashAutoSubmit) {
          ptyProc.write('\r');
          seqDbg(isSlash ? 'sent body+enter (slash autosubmit)' : 'sent body+enter');
          if (isSlash && slashDoubleEnter) {   // 無人自動時のみ旧 double-enter 退避 (A/B 用)
            await gateType();
            ptyProc.write('\r');
            seqDbg('sent 2nd enter (legacy double)');
          }
        } else {
          seqDbg('slash typed; enter left to user (manual submit, 2026-06-01 design)');
          console.error(chalk.cyan('  [SEQ] /effort をボックスに投入しました → Enter キーで適用してください。'));
        }
      } catch (e) { seqDbg(`error ${e && e.message}`); }
      if (i < initialCommands.length - 1) await gateSeq();
    }
    seqDbg('done');
  };
  submitSequence().catch(() => {});

  // PTY 終了待ち + 後始末
  // 注意 (2026-05-31 「/exit 後 PowerShell に戻らない」修正): node-pty は
  // Windows/ConPTY で「子シェルが自分で終了 (= /exit) すると onExit は発火するのに
  // 親プロセス (winpty-agent/conhost) と libuv ハンドルが残り node プロセスが
  // 終了しない」既知バグがある (microsoft/node-pty #333 / #413)。onExit 内で
  // ptyProc.kill() を呼び ConPTY を明示的に閉じてハンドルを解放する。
  // 二重 kill は例外を投げうるため try/catch で握り潰す。最終的なプロセス終了の
  // 保証はメインループ正常終了時の process.exit(0) で担保する。
  // 終了待ち + 後始末。cleanup は onExit と Ctrl+C(SIGINT) の双方から呼ばれうるため
  // settled ガードで一度だけ実行する。
  // 重要 (workflow 検証 high finding 2026-05-31): onExit は conout socket の 'close'
  // 由来で、ConPTY が drain デッドロック (microsoft/node-pty #375 / #1810) を起こすと
  // 発火せずこの Promise が解決しない。その状態を Ctrl+C で抜けたとき端末復元 (raw mode /
  // win32-input-mode 無効化) が走らないと次回 ccr の selectProject 入力が化ける。そこで
  // SIGINT でも必ず cleanup を通し、端末を復元してからプロセスを終える。
  await new Promise((resolve) => {
    let settled = false;
    const cleanup = (viaSignal) => {
      if (settled) return;
      settled = true;
      try { process.removeListener('SIGINT', onSigint); } catch {}
      try { watcher.close(); } catch {}
      try { stdin.removeListener('data', onInput); } catch {}
      try { process.stdout.removeListener('resize', onResize); } catch {}
      if (stdin.isTTY) { try { stdin.setRawMode(wasRaw); } catch {} }
      try { stdin.pause(); } catch {}
      try { ptyProc.kill(); } catch {}   // 残留 ConPTY/agent プロセスを掃除
      // ConPTY が有効化した win32-input-mode 等が端末に残ると次回 ccr の
      // selectProject や復帰した pwsh プロンプトの入力が化ける。明示的に無効化する。
      resetTerminalInput();
      resolve();
      // Ctrl+C 経由はメインループ末尾の process.exit(0) に乗らないため、
      // 端末復元後にここで明示終了する (130 = 128+SIGINT)。
      if (viaSignal) { try { process.exit(130); } catch {} }
    };
    const onSigint = () => cleanup(true);
    try { process.on('SIGINT', onSigint); } catch {}
    ptyProc.onExit(() => cleanup(false));
  });
}

// ─── セッション実行 ───────────────────────────────────────────
async function runSession(projectPath, sessionNum, projects) {
  const tag = projectPath ? `[${path.basename(projectPath)}]` : '[汎用]';
  console.error(chalk.blue(
    `\n[${new Date().toLocaleTimeString('ja-JP')}] ▶ セッション #${sessionNum} ${tag}`
  ));

  await writeSessionConfig(projectPath, projects);

  const docs = projectDocs(projectPath);
  await fs.ensureDir(docs.dir);

  const hasSummary = !!(projectPath && await fs.pathExists(docs.summary));
  if (hasSummary) {
    console.error(chalk.gray(`  [RESTORE] docs/SESSION_SUMMARY.md を引き継ぎます`));
  }

  await fs.remove(SIGNAL_FILE).catch(() => {});

  const env = { ...process.env };
  if (projectPath) env.RAPTOR_CALLER_DIR = projectPath;

  // ccr 起動時は常に ultracode effort を有効化する (ユーザー指示 2026-05-31)。
  // effort フラグ (--effort) は ultracode 非対応 (low/medium/high/xhigh/max のみ。実機検証済) で、
  // initial prompt に '/effort ultracode\n\n<本文>' と連結すると Claude Code が
  // 単一 positional プロンプトの先頭スラッシュとして本文全体を引数化し
  // "Invalid argument: ultracode" を起こす。よって node-pty 経由で
  // '/effort ultracode' と復元プロンプトを別々の submission として順次投入する。
  const initialCommands = buildInitialCommands(hasSummary);
  if (initialCommands.length) {
    console.error(chalk.gray(`  [SEQ] 初期コマンド ${initialCommands.length} 件を順次投入します (先頭: ${initialCommands[0].slice(0, 40)})`));
  }

  // テスト用: RAPTOR_AUTO_CLAUDE_ARGS (空白区切り) で起動引数を差し替え可能 (E2E でモックを spawn)。
  // 未設定なら従来どおり (既定挙動は不変)。
  const args = process.env.RAPTOR_AUTO_CLAUDE_ARGS
    ? process.env.RAPTOR_AUTO_CLAUDE_ARGS.split(' ').filter(Boolean)
    : ['--dangerously-skip-permissions'];

  try {
    await runClaudeWithPty(CLAUDE_EXE, args, env, initialCommands);
  } catch { /* 予期せぬエラー */ }
}

// ─── メインループ ─────────────────────────────────────────────
const projects = await discoverProjects();
const projectPath = await selectProject();
let sessionNum = 0;

while (true) {
  sessionNum++;
  await runSession(projectPath, sessionNum, projects);

  if (await fs.pathExists(SIGNAL_FILE)) {
    await fs.remove(SIGNAL_FILE);

    const docs = projectDocs(projectPath);
    if (await fs.pathExists(docs.summary)) {
      const date = new Date().toISOString().slice(0, 10);
      const archive = path.join(docs.dir, `SESSION_SUMMARY_${date}.md`);
      await fs.copy(docs.summary, archive, { overwrite: true });
      console.error(chalk.yellow(`\n[ROTATE] docs/SESSION_SUMMARY.md → SESSION_SUMMARY_${date}.md にアーカイブ`));
    }

    console.error(chalk.cyan(`[ROTATE] 3秒後に新セッション起動...`));
    await sleep(3000);
  } else {
    console.error(chalk.gray(`\n[SYSTEM] セッション #${sessionNum} 正常終了`));
    await fs.remove(SESSION_CFG).catch(() => {});
    break;
  }
}

// node-pty (Windows/ConPTY) は子終了後も内部ハンドル/親プロセスが libuv イベント
// ループに残り、break でループを抜けてもスクリプトが自然終了せず PowerShell に
// プロンプトが返らない (microsoft/node-pty #333 / #413)。端末状態は onExit cleanup で
// 復元済みなので、ここで明示的にプロセスを終了させて制御をシェルへ返す。
// 端末のリッチ入力モードも念のため無効化してから返す (pwsh プロンプトの保護)。
resetTerminalInput();
process.exit(0);

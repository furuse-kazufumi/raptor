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
 *   注意 (2026-05-31 連結バグ再発で判明): スラッシュコマンドを打つと TUI の
 *   オートコンプリートメニューが開き、その状態の Enter(\r) は「送信」でなく
 *   「メニュー確定」として吸収され送信されない。直後に次コマンド本文が同じ
 *   入力欄へ追記され `/effort ultracode<本文>` と連結→ Invalid argument で停止する。
 *   対策: 各コマンド投入の前に Esc(\x1b=メニュー閉) + Ctrl+U(\x15=行クリア) で
 *   入力欄を必ず空にし、スラッシュコマンドは Enter を 2 回送る (1 回目がメニューに
 *   吸収されても 2 回目で送信)。万一 effort 投入に失敗しても次コマンド投入前の
 *   行クリアで連結は起きず、最悪 effort 不適用で済む (フリーズしない)。
 *   詳細仕様: docs/CCR_AUTO_RESTART.md
 */

import { createInterface } from 'readline';
import { createRequire } from 'module';

// node-pty (prebuilt fork) をスクリプト基準で解決する。zx の require ではなく
// createRequire を使い、raptor/node_modules を確実に参照させる。
const nodeRequire = createRequire(import.meta.url);

const SCRIPT_DIR    = path.dirname(process.argv[1]);
// On Windows use PowerShell so claude.exe is found via PATH
if (process.platform === 'win32') {
  $.shell = 'pwsh.exe';
  $.prefix = '';
}

const CLAUDE_EXE = (() => {
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
// 順序: /effort <level> → (任意 preCommands) → 復元プロンプト。
// RAPTOR_AUTO_EFFORT_LEVEL='' で effort 投入を無効化。
// RAPTOR_AUTO_PRECOMMANDS は '||' 区切りで追加コマンドを差し込める
//   (例: '/workflow foo||前置きコメント') — /effort と復元の間に入る。
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

  if (hasSummary) {
    cmds.push(
      'セッション再開。CLAUDE.md SESSION START を実行し、SESSION_SUMMARY.md から前回作業を復元して即座に自律継続してください。「進めますか？」「選択肢」「どれを進めますか」のような確認・メニュー提示はせず、宣言してそのまま着手すること。'
    );
  }
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
  const FIRST_DELAY_MS = Number(process.env.RAPTOR_AUTO_PTY_FIRST_DELAY_MS || 2500); // TUI 起動待ち
  const TYPE_DELAY_MS  = Number(process.env.RAPTOR_AUTO_PTY_TYPE_DELAY_MS  || 350);  // テキスト反映待ち
  const SEQ_DELAY_MS   = Number(process.env.RAPTOR_AUTO_SEQ_DELAY_MS       || 1500); // submission 間隔

  const cols = process.stdout.columns || 120;
  const rows = process.stdout.rows || 30;

  const ptyProc = ptyLib.spawn(file, args, {
    name: 'xterm-256color',
    cols, rows,
    cwd: process.cwd(),
    env,
  });

  // PTY → 実端末
  const onData = d => process.stdout.write(d);
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
  //   (a) Esc(\x1b)  … 直前に残ったオートコンプリート/ピッカーを閉じる
  //   (b) Ctrl+U(\x15) … 入力欄を空にする (前コマンドの submit 失敗時の残骸除去=連結防止)
  //   (c) 本文を流し込む → 反映待ち
  //   (d) Enter(\r) で submit。スラッシュコマンドはメニューが 1 回目の Enter を
  //       吸収しうるため 2 回送る (2 回目で確実に送信。空欄での余分な Enter は no-op)。
  // この (a)(b) により、たとえ effort 投入が失敗しても次コマンドと連結せず、
  // 最悪 effort 不適用で済む (= Invalid argument フリーズを構造的に防ぐ)。
  const submitSequence = async () => {
    if (!initialCommands.length) return;
    await sleep(FIRST_DELAY_MS);
    for (let i = 0; i < initialCommands.length; i++) {
      const cmd = String(initialCommands[i]);
      const isSlash = cmd.trimStart().startsWith('/');
      console.error(chalk.gray(`  [SEQ] 投入 [${i + 1}/${initialCommands.length}]${isSlash ? ' (slash)' : ''}: ${cmd.split('\n')[0].slice(0, 60)}`));
      try {
        ptyProc.write('\x1b');            // (a) メニュー/ピッカーを閉じる
        await sleep(TYPE_DELAY_MS);
        ptyProc.write('\x15');            // (b) 入力欄をクリア (残骸除去=連結防止)
        await sleep(TYPE_DELAY_MS);
        ptyProc.write(cmd);              // (c) 本文投入
        await sleep(TYPE_DELAY_MS);
        ptyProc.write('\r');             // (d) submit
        if (isSlash) {                    //     メニューが Enter を吸収した場合の保険
          await sleep(TYPE_DELAY_MS);
          ptyProc.write('\r');
        }
      } catch {}
      if (i < initialCommands.length - 1) await sleep(SEQ_DELAY_MS);
    }
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
  await new Promise((resolve) => {
    ptyProc.onExit(() => {
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
    });
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

  const args = ['--dangerously-skip-permissions'];

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

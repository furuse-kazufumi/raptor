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
 */

import { createInterface } from 'readline';

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

// ─── セッション実行 ───────────────────────────────────────────
async function runSession(projectPath, sessionNum, projects) {
  const tag = projectPath ? `[${path.basename(projectPath)}]` : '[汎用]';
  console.error(chalk.blue(
    `\n[${new Date().toLocaleTimeString('ja-JP')}] ▶ セッション #${sessionNum} ${tag}`
  ));

  await writeSessionConfig(projectPath, projects);

  const docs = projectDocs(projectPath);
  await fs.ensureDir(docs.dir);

  if (await fs.pathExists(docs.summary)) {
    console.error(chalk.gray(`  [RESTORE] docs/SESSION_SUMMARY.md を引き継ぎます`));
  }

  await fs.remove(SIGNAL_FILE).catch(() => {});

  const env = { ...process.env };
  if (projectPath) env.RAPTOR_CALLER_DIR = projectPath;

  // SESSION_SUMMARY.md があるプロジェクトを選んだ場合は初回プロンプトを自動投入し、
  // ユーザが「再起動しましたがどうでしょうか？」等を毎回打たなくても
  // SESSION START → 前回作業の自律継続が走るようにする。
  const args = ['--dangerously-skip-permissions'];
  if (projectPath && await fs.pathExists(docs.summary)) {
    args.push(
      'セッション再開。CLAUDE.md SESSION START を実行し、SESSION_SUMMARY.md から前回作業を復元して即座に自律継続してください。「進めますか？」「選択肢」「どれを進めますか」のような確認・メニュー提示はせず、宣言してそのまま着手すること。'
    );
    console.error(chalk.gray(`  [AUTO-RESUME] 初回プロンプト自動投入で SESSION START を起動します`));
  }

  try {
    const { spawn } = await import('child_process');
    const { watch } = await import('fs');
    await new Promise((resolve) => {
      const child = spawn(CLAUDE_EXE, args, {
        stdio: 'inherit',
        env,
        shell: false,
      });

      // .rotate-signal が作成されたら Claude を自動終了させる
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

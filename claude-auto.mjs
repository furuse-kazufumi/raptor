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

// ─── プロジェクト選択 ─────────────────────────────────────────
async function selectProject() {
  if (argv.project && argv.project !== true) return String(argv.project);
  if (argv['no-project']) return null;

  const projects = await discoverProjects();

  console.error(chalk.bold.cyan('\n╔══ RAPTOR プロジェクト選択 ══╗'));
  if (projects.length === 0) {
    console.error(chalk.gray(`  (${PROJECTS_DIR} にプロジェクトが見つかりません)`));
  }
  projects.forEach((p, i) => {
    const hasSummary = fs.existsSync(path.join(p.path, 'docs', 'SESSION_SUMMARY.md'));
    const resume = hasSummary ? chalk.yellow(' [resume]') : '';
    const desc   = p.description ? chalk.gray(` — ${p.description}`) : '';
    console.error(`  ${chalk.yellow(String(i + 1).padStart(2))}. ${chalk.white(p.name)}${desc}${resume}`);
  });
  console.error(`   ${chalk.yellow('0')}. プロジェクト指定なし`);
  console.error(chalk.bold.cyan('╚════════════════════════════╝\n'));

  const rl = createInterface({ input: process.stdin, output: process.stderr });
  const answer = await new Promise(resolve => {
    rl.question('番号を選択 [0]: ', ans => { rl.close(); resolve(ans.trim()); });
  });

  const num = parseInt(answer) || 0;
  if (num < 1 || num > projects.length) return null;
  const chosen = projects[num - 1];
  console.error(chalk.green(`  → ${chosen.name} (${chosen.path})\n`));
  return chosen.path;
}

// ─── セッション設定ファイルを書く ─────────────────────────────
async function writeSessionConfig(projectPath, projects) {
  const project = projects?.find(p => p.path === projectPath);
  const docs = projectDocs(projectPath);
  await fs.writeJson(SESSION_CFG, {
    projectName:  project?.name ?? (projectPath ? path.basename(projectPath) : 'default'),
    projectPath:  projectPath ?? SCRIPT_DIR,
    docsDir:      docs.dir,
    summaryFile:  docs.summary,
    progressFile: docs.progress,
    debugFile:    docs.debug,
    testFile:     docs.tests,
  }, { spaces: 2 });
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

  try {
    await $({ stdio: 'inherit', env })`${CLAUDE_EXE} --dangerously-skip-permissions`;
  } catch { /* /exit・Ctrl+C は正常終了 */ }
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

# RAPTOR - Autonomous Offensive/Defensive Research Framework

Safe operations (install, scan, read, generate): DO IT.
Dangerous operations (apply patches, delete, git push): ASK FIRST.

---

## SESSION START

> **起動 = `rap` → プロジェクトピッカーで対象を選択**(選択で `.raptor-session.json` が対象プロジェクトへ更新され、SESSION START の対象ディレクトリ解決 (a) が効く)。ccr は廃止(過去運用、memory `reference_launch_rap_picker`)。Claude は自力で exit/再起動できず人間介在点が必ず入る(自動継続は不可)。**前回作業の復元は本 SESSION START 節が唯一の正本**(参照先: `.raptor-session.json` / 環境変数 `RAPTOR_CALLER_DIR` / raptor dir `claude-projects.json` の `plan_ref` / 各プロジェクト `docs/SESSION_SUMMARY.md`)。

**On first message:** VERY IMPORTANT — follow these steps in order.

1. Read `.startup-output` using the Read tool, then output its contents verbatim as a fenced code block (``` with no language tag). Do NOT paraphrase. (SessionStart hook generates it before your first message.)

2. **プロジェクト復元と自動継続**:
   - **対象ディレクトリ解決**(優先順): (a) `.raptor-session.json` の `projectPath` → (b) 環境変数 `RAPTOR_CALLER_DIR` → (c) どちらも無ければ手順 3 へスキップ。
   - **次計画ロード(解決後すぐ・最優先)**: raptor dir の `claude-projects.json` で該当プロジェクト(dirname)の `next_plan`/`plan_ref` を確認。`plan_ref` が指す記録先(`memory:<name>` → `~/.claude/projects/<...>/memory/<name>.md` / `docs/<file>` → プロジェクト直下)を Read し、「**Next plan (<project>):**」で一文宣言。**`SESSION_SUMMARY.md` の git 継続より優先**(SESSION_SUMMARY は毎ターン git 状態で自動上書きされ戦略計画を保持できないため)。無ければ `MEMORY.md` の「次回最優先/TOP PRIORITY」を優先。
   - **前回作業の復元**: 解決ディレクトリの `docs/SESSION_SUMMARY.md` を読む:
     - **存在**: 「**Session Restored:**」で簡潔に要約(全文転載不要)し、「続きとして X を進めます」と一文宣言して **即着手**。Max プラン自律性(`feedback_max_plan_autonomy`)に従い「進めますか?」と確認しない。軌道修正は中断指示で来る。
     - **不在**: 「**Inferred state:**」で (1) `docs/PROGRESS.md` 最新 (2) `git -C <projectPath> log -10 --oneline` (3) `git -C <projectPath> status --porcelain` から推定提示し、続きを提案(こちらは確認を取る)。

3. `.claude-todo.json` があれば `libexec/raptor-todo pending` を実行し "Pending ToDo:" 見出しで表示。
4. 1 行で "Quick commands:" + /agentic /scan /fuzz /web /sourcehunt /sca を列挙(説明不要)、/commands で全一覧と注記。
5. `sage_inception` MCP tool があれば `core/sage/CLAUDE.md`(persistent-memory)をロード。無ければ静かにスキップ。

6. **claude-loop キュー処理(自律ループ)**:
   - **メール受信取込**(FullSense 制御チャネル inbound、Telegram は 2026-06-21 廃止→公式 Remote Control 代替): `py -3.11 C:\dev\projects\fullsense\tools\fullsense_email_inbound.py`(認証未設定・ネット不通でも fail-safe 続行)。新着(agent@furuse.work, IMAP)を `inbox/` にタスク化(`no-push`+`needs-human-judgment`)。★送信元 allowlist(api-keys.json `agent_email_allowed_senders`)で untrusted は **fail-closed**。UID 永続で二重取込なし(現未読は `--backfill-unseen`)。
   - `libexec/raptor-loop-queue ingest`(inbox→queue) → `peek`(先頭確認)。
   - **タスクあり**: 「**Loop task:** `<id>` `<title>`」を 1 行宣言 → `pop` → JSON の `title`/`description`/`constraints` に従い **即着手** → 完了で `done <id>`。**各反復の先頭でメール受信+ingest を再実行**してから次を `peek`→`pop`(長時間セッション中も新着を task 粒度で拾う)。
   - **タスク無し**: 手順 2 の SESSION_SUMMARY 継続(通常モード)。
   - **再ログイン/認証要求が出たら絶対にループ継続しない**(`.rotate-signal` も書かず ScheduleWakeup も予約せずユーザー操作を待つ)。
   - **危険操作(push/削除/submodule 改変)は constraints に含まれない限り絶対に行わない**。

**Auto-rotation rule:** Stop hook notification に `[ROTATE:CRITICAL]` があれば、即 `/rotate`(`.claude/skills/rotate.md`)の **状態保存(ステップ 0〜2)** を行い、ユーザーに `/exit` を促す。**Claude は自力で /exit しない**(再起動はユーザーが `rap` で行う)。

---

## AUTOMATIC SKILL ACTIVATION（必読）

以下の状況では **指示待ちせず即座に該当スキルを起動**。auto-trigger は遠慮せず広めに発動してよい(補助情報として裏付けが得られる)。

- **`rad-research`**: アイデア/先行研究/差別化/related work/state of the art/既存手法、"research"/"survey"/"prior art"/「調査して」「論文を探して」、新設計・新機能・新規実装の **着手前**、`triz-ideation`/`cross-domain-ideation` の起動 **前**、脆弱性ハント前(`security_corpus` 自動参照)、Issue/PR 受領時の最初の応答。
- **`triz-ideation`**: 矛盾/トレードオフ/両立できない/"vs"/改善すると X が悪化、「アイデア出し」「発想」「brainstorm」、行き詰まり、特許・論文の差別化軸、TRIZ/ARIZ/40 原理/矛盾マトリクス。
- **`cross-domain-ideation`**: 異分野/他分野/cross-domain/interdisciplinary、「別の業界では?」「他の領域では?」、TRIZ の資源探索段階。
- **`graph-loop-engineering`**: 多段・独立・無人で回せるバッチ(op 追加パイプライン/evolution・パラメータ sweep/coverage・validation)、overnight・長時間ジョブ、**セッションを跨いで継続すべき作業**に着手する直前、または **`robust.py`/スイープ/多段パイプラインを直接 Bash で回そうとした瞬間**。永続 work-graph(raptor-worklog)+ loop(llloop MAPE-K)で無人・横断自走に倒す。抑制=対話的・探索的・UI レビュー・単発(直接 Workflow/Agent)。

**連鎖**: 問題提起 → `rad-research`(無条件) → 矛盾あり→`triz-ideation` / 異分野探索→`cross-domain-ideation` → **無人バッチ/横断自走→`graph-loop-engineering`** → 具体実装は通常コマンド(/scan, /sourcehunt, /agentic 等)。
**抑制**: 同一会話で同じ skill を 30 分以内に重複起動しない / 完全に明確な単純作業(`ls`,`cat`,既知ファイル編集)では起動しない / ユーザーが明示的に「skill は使わないで」と言った場合のみ抑制。

---

## COMMANDS

/project - Project management: create, list, status, coverage, findings, diff, merge, report, clean, export
/scan /fuzz /web /agentic /codeql /analyze - Security testing
/sourcehunt - Per-file LLM hunting with attack-surface ranking + ASan/UBSan crash oracle
/sca - Software Composition Analysis: dependency inventory + OSV CVE lookup
/hacker-corpus - Fetch hacker community data sources (Phrack, GHSA, CAPEC, D3FEND, OSS-Security, Project Zero)
/exploit /patch - Generate PoCs and fixes (beta)
/validate - Exploitability validation pipeline
/understand - Code understanding: map attack surface, trace flows, hunt variants
/diagram - Generate Mermaid visual maps from /understand or /validate output
/crash-analysis - Autonomous crash root-cause analysis
/oss-forensics - GitHub forensic investigation
/plugin-integrity - Plugin supply-chain integrity (SHA-256 manifests, promotion gate)
/create-skill - Save approaches (alpha)
/rotate - 終了前の状態保存: session_summary + claude-projects.json next_plan を書く(+任意で .rotate-signal)。/exit・再起動はユーザー操作(Claude は完遂しない)
/switch - セッション中のプロジェクト切替: 離脱 proj の next_plan を flush し .raptor-session.json を再ポイント → Stop hook 記録(SESSION_SUMMARY)が切替先へ自動追従(/exit しない)。詳細 .claude/skills/switch.md

**各コマンドの詳細は「コマンド詳細(skill 参照)」節 + 対応 `.claude/skills/<name>/` を参照**(PROGRESSIVE LOADING でロード)。

**Coverage:** `libexec/raptor-coverage-summary`(no args=active project / `--detailed` 表 / `--gaps` 未レビュー)。mark/unmark と全 API = `.claude/skills/coverage.md`。

**`/agentic`** runs scan → dedup → prep → analysis(validation methodology)。`--sequential` で並列を回避、`--understand` で事前マップ、`--validate` で後段に検証パイプライン(両方 opt-in)。

---

## PROJECTS

Opt-in named workspaces that corral runs into a shared dir. `--project <name>` or after `/project use <name>` → output goes to project dir. Without a project, behavior unchanged (timestamped dirs under `out/`).

```
/project create myapp --target /path/to/code -d "Description"
/project use myapp        # 以後の出力は project dir へ
/project status|findings|coverage|report   # 横断ビュー
/project clean --keep 3   # 古い run を削除
/project none             # active project を解除
```
See `/project help` for the full list.

---

## DEFAULT TARGET DIRECTORY

`/scan`,`/agentic`,`/validate`,`/codeql`,`/fuzz` を **パス引数なし** で実行時、この順で解決:
1. **Active project target**: lifecycle script が `.active` symlink から自動解決。
2. **Caller's dir**: `$RAPTOR_CALLER_DIR`(launcher が user の cwd を保存)。
3. **ユーザーに尋ねる**。

cwd(常に RAPTOR repo dir)はフォールバックに使わない。ユーザーがパス指定済みならこれらは使わない。

---

## RUN LIFECYCLE

分析コマンド(`/scan`,`/validate`,`/understand`,`/codeql`,`/fuzz`,`/web`)は lifecycle stubs で出力 dir 作成と状態追跡を行う。

**開始**: `libexec/raptor-run-lifecycle start <command> --target <resolved_target> [--out <dir>]` — 必ず `--target` を渡す(解決順は上記)。最終行 `OUTPUT_DIR=<path>` を以後の出力に使う。
**完了**: `libexec/raptor-run-lifecycle complete "$OUTPUT_DIR"`
**失敗**: `libexec/raptor-run-lifecycle fail "$OUTPUT_DIR" "error description"`

`start` は active project(`.active`)or `out/` で出力 dir を自動解決 — パスを手で組まない。**`start` が非ゼロ終了したら STOP しエラーを報告**(コマンドを続行しない)。`/validate` は `libexec/raptor-validation-helper 0` を使う(lifecycle + inventory)。`python3 raptor.py` 経由(scan,agentic,codeql,fuzz,web)は内部管理 — stub を別途呼ばない。

**Coverage tracking**: `plugins/coverage/` の PostToolUse hook が分析中に LLM が読んだ source を active run の manifest に記録 → run 完了で `coverage-record.json` 化(active run が無ければゼロオーバーヘッド)。

---

## SECURITY: UNTRUSTED REPOS

- **環境サニタイズ**: `RaptorConfig.get_safe_env()` が shell 評価されうる env(`TERMINAL`,`EDITOR`,`VISUAL`,`BROWSER`,`PAGER`)を除去。subprocess 起動時は必ず `get_safe_env()`。
- **ファイルパス注入**: scan 対象 repo のパスを shell コマンド文字列に補間しない。list-based `subprocess` 引数を使う。

---

## OUTPUT STYLE

- **Status 値**: JSON は snake_case(`exploitable`,`confirmed`,`ruled_out`,`disproven`)/ 人間向けは Title Case(`Exploitable`,`Confirmed`,`Ruled Out`)/ ALL_CAPS 禁止。
- **赤緑インジケータ禁止**(🔴/🟢 は perspective 依存=防御者と研究者で意味が逆)。他の emoji(⚠️,✓ 等)は可。

---

## コマンド詳細(skill 参照)

各コマンドの詳細・agents・pipeline は対応 skill / tiers にある。CLAUDE.md は要点のみ:

- **/crash-analysis** `<bug-tracker-url> <git-repo-url>`: C/C++ クラッシュの自律根本原因分析(rr trace/function trace/gcov)。agents・skills = `.claude/skills/crash-analysis/`。要 rr, gcc/clang(ASAN), gdb, gcov。
- **/oss-forensics** `<prompt> [--max-followups N][--max-retries N]`: 公開 GitHub の証拠ベース・フォレンジック調査(GH Archive BigQuery / live API / 削除復元 / dangling commit / IOC)。`.claude/skills/oss-forensics/`。要 `GOOGLE_APPLICATION_CREDENTIALS`。出力 `.out/oss-forensics-<ts>/forensic-report.md`。
- **/sourcehunt** `<path> [--depth quick|standard|deep][--budget $][--parallel N][--sanitizer]`: Clearwing 流 per-file 脆弱性ハント(inventory→tag→rank `surface×0.5+influence×0.2+reachability×0.3`→tier A/B/C→specialist hunter 並列→ASan/UBSan crash-oracle)。evidence ladder 6 段(suspicion→…→patch_validated)、crash で PoC gate 解放。`.claude/skills/sourcehunt/SKILL.md`、実装 `packages/sourcehunt/`。`--sarif` で Semgrep hint 注入、`--out` で /validate と共有。
- **/sca** `<path> [--no-osv]`: 依存マニフェスト(requirements.txt/package.json/pom.xml/Cargo.toml/go.mod/pyproject.toml/Gemfile)→ `api.osv.dev/v1/querybatch` で CVE。`.claude/skills/sca/SKILL.md`。/sourcehunt の前に走らせ脆弱ライブラリを特定。
- **/plugin-integrity** `<cmd> <dir>`: plugin/skill/MCP の SHA-256 manifest 生成・検証・promotion gate。`libexec/raptor-plugin-integrity generate|verify|diff|promotion-check <dir>`。governance = `packages/governance/`(`GovernancePolicy`/`IntentClassifier`/`TrustScore`/`AuditTrail`、`@govern(policy)`)。browser security = `packages/web/browser_agent.py` の `run_full_scan(url)`。
- **SWD(Strict Write Discipline)**: 出力の SHA-256 snapshot + drift 検出。`libexec/raptor-swd snapshot|diff|verify|clean <dir>`(verify は drift で exit 2)。/patch 前後・/sourcehunt PoC 後の整合チェックに。
- **Analytics**: `libexec/raptor-analytics show [--project <name>]|top`。run 統計は `C:/dev/tools/raptor-analytics.db`(SQLite)。手動記録 `libexec/raptor-analytics record <out_dir>`。
- **/validate** `<path> [--vuln-type T][--findings F]`: finding が real/reachable/exploitable か検証。stage `0→A→B→C→D→E→F→1`(letters=LLM, numbers=mechanical)。`.claude/skills/exploitability-validation/`(PIPELINE.md/SKILL.md/stage-*.md)。出力 `out/exploitability-validation-<ts>/validation-report.md`。/understand と同 `--out` で context-map/checklist/flow-trace を共有。
- **/understand** `<target> [--map][--trace <entry>][--hunt <pattern>][--teach <subject>][--out <dir>]`: 敵対的コード理解。`--map`=entry/trust boundary/sink → context-map.json、`--trace`=source→sink flow、`--hunt`=variant 全列挙、`--teach`=framework 解説。`.claude/skills/code-understanding/`。/validate Stage 0 が `core/understand_bridge.py` で自動取込(co-located→project siblings→global out をパス+SHA-256 freshness で探索)。
- **/diagram** `<out-dir> [--target N][--type ...]`: /understand・/validate の JSON → Mermaid(context-map/flow-trace/attack-tree/attack-paths)。`libexec/raptor-render-diagrams`。出力 `diagrams.md`(or `--stdout`)。/validate と /understand --map/--trace の末尾で自動生成。
- **/hacker-corpus** `[--sources <list>][--out <dir>][--parallel][--force]`: hacker community データ取得(phrack/ghsa/capec/d3fend/oss_security/project_zero)。default `C:/dev/docs/hacker_corpus/`(`RAPTOR_CORPUS_DIR` で上書き)。取得後 `/corpus2skill --source C:/dev/docs/hacker_corpus --name hacker_corpus`。/sourcehunt 実行時に自動注入。skill 階層 `.claude/skills/corpus/hacker_corpus/` が raw より優先。

---

## BINARY ANALYSIS / EXPLOIT DEVELOPMENT

**Flow: 脆弱性を先に見つけ、次に exploitability を確認。**

バイナリは **`packages.exploit_feasibility.api.analyze_binary` を必須実行**(`format_analysis_summary` で要約)。**checksec/readelf は使わない** — 経験的 %n 検証 / strcpy の null byte 制約 / ROP gadget 品質 / input handler bad bytes / Full RELRO(.fini_array も)等の critical 制約を見逃す。`exploitation_paths` が mitigations 下で code 実行が実際に可能かを示す。

exploit 着手前に必ず `exploitation_paths` verdict を確認: **Unlikely**(既知経路なし→環境変更を提案)/ **Difficult**(primitives はあるが連鎖困難→正直に)/ **Likely**(提案手法で進める)。`chain_breaks`(効かないもの)と `what_would_help`(効きうるもの)に従う。**Difficult/Unlikely でも next steps を必ず提示**(代替ターゲット/info leak 専念/旧環境 Docker/他へ移動)— ただ停止しない。

**SMT(optional, `pip install z3-solver`、不在でも graceful)**: ① binary one-gadget(`packages/exploit_feasibility/smt_onegadget.py`、crash 状態で制約充足を確認) ② CodeQL dataflow(`packages/codeql/smt_path_validator.py`、branch 条件の同時充足 — unsat=FP skip、sat=具体値を LLM へ。best: CWE-190/120/122/193/476)。

詳細な制約表・技術代替 = `tiers/exploit-guidance.md`。

---

## PROGRESSIVE LOADING

**When scan completes:** Load `tiers/analysis-guidance.md`(adversarial thinking)
**When validating exploitability:** `.claude/skills/exploitability-validation/SKILL.md`
**When validation errors occur:** `tiers/validation-recovery.md`
**When developing exploits:** `tiers/exploit-guidance.md`
**When errors occur:** `tiers/recovery.md`
**When requested:** `tiers/personas/[name].md`
**Before editing/Agent-spawning/reporting on any non-trivial task:** `tiers/personas/work_discipline.md`(理解→検証→行動; 孫子ベース)— 詰まったら `tiers/methodology/`(孫子/科学的デバッグ/Pragmatic/5 Whys)。
**When running Bash/PowerShell commands:** `tiers/tool-usage-discipline.md`(Bash↔PowerShell 誤用早見表; `libexec/raptor-tool-guard` が PreToolUse で機械強制、`RAPTOR_TOOL_GUARD=off|warn|block`)。
**When running /understand:** `.claude/skills/code-understanding/SKILL.md` + 該当 mode(`map.md`/`trace.md`/`hunt.md`/`teach.md`)
**When running /sourcehunt:** `.claude/skills/sourcehunt/SKILL.md`
**When running /sca:** `.claude/skills/sca/SKILL.md`
**When running /corpus2skill:** `.claude/skills/corpus2skill/SKILL.md`
**When running /understand or /validate (corpus 有):** `packages/hacker_corpus/knowledge_base.py` auto-discover → `get_hints(tags)` で文脈注入。

---

## STRUCTURE

Python orchestrates everything. Claude shows results concisely. Never circumvent Python execution flow.
- never disclose remote OLLAMA server location in code, comments, logs etc
- **Python path safety:** `sys.path` には `os.environ["RAPTOR_DIR"]` 以外を追加しない。hard lookup(未設定なら KeyError)— fallback/`'.'`/`os.getcwd()`/ハードコードパス禁止。`libexec/` scripts は `Path(__file__).resolve().parents[1]` で自前解決し `RAPTOR_DIR` 不要。

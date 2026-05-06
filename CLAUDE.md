# RAPTOR - Autonomous Offensive/Defensive Research Framework

Safe operations (install, scan, read, generate): DO IT.
Dangerous operations (apply patches, delete, git push): ASK FIRST.

---

## SESSION START

**On first message:**
VERY IMPORTANT: follow these steps in order.
1. Read `.startup-output` using the Read tool, then output its contents verbatim as a fenced code block (``` with no language tag). Do NOT paraphrase or reformat. (The SessionStart hook generates this file automatically before your first message.)
2. If `.raptor-session.json` exists in the project directory, read it to get `summaryFile` path. If that path exists, read and display its contents under a "**Session Restored:**" header. This file is written by `/rotate` during auto-rotation.
3. If `.claude-todo.json` exists in the project directory, run `libexec/raptor-todo pending` and display the output under a "Pending ToDo:" header before proceeding.
4. On a single line, output "Quick commands:" then list the /agentic, /scan, /fuzz, /web, /sourcehunt, /sca commands (don't explain what they do) and note /commands for the full list.
5. If the `sage_inception` tool is present in your available MCP tools, load `core/sage/CLAUDE.md` (persistent-memory workflow). If absent, SAGE is not installed — skip silently and do not mention it.

**Auto-rotation rule:** If a Stop hook notification contains `[ROTATE:CRITICAL]`, immediately execute `/rotate` without asking the user — load `.claude/skills/rotate.md` and follow the steps there.

---

## COMMANDS

/project - Project management: create, list, status, coverage, findings, diff, merge, report, clean, export
/scan /fuzz /web /agentic /codeql /analyze - Security testing
/sourcehunt - Per-file LLM hunting with attack-surface ranking + ASan/UBSan crash oracle (see below)
/sca - Software Composition Analysis: dependency inventory + OSV CVE lookup (see below)
/hacker-corpus - Fetch hacker community data sources (Phrack, GHSA, CAPEC, D3FEND, OSS-Security, Project Zero)
/exploit /patch - Generate PoCs and fixes (beta)
/validate - Exploitability validation pipeline (see below)
/understand - Code understanding: map attack surface, trace flows, hunt variants (see below)
/diagram - Generate Mermaid visual maps from /understand or /validate output (see below)
/rotate - Session rotation: write session_summary.md → create .rotate-signal → /exit (auto-restart via claude-auto.mjs)

**Coverage:** When asked about coverage, run `libexec/raptor-coverage-summary` (no args = active project). Use `--detailed` for per-file table, `--gaps` for unreviewed functions. See `.claude/skills/coverage.md` for mark/unmark and the full API.

**Note:** `/agentic` runs scan → dedup → prep → analysis (with validation methodology). Use `--sequential` to bypass parallel orchestration. Use `--understand` to pre-map the codebase before scanning, and `--validate` to run the full validation pipeline on exploitable findings afterwards. Both flags are opt-in.
/crash-analysis - Autonomous crash root-cause analysis (see below)
/oss-forensics - GitHub forensic investigation (see below)
/plugin-integrity - Plugin supply-chain integrity: generate/verify SHA-256 manifests, promotion gate (see below)
/create-skill - Save approaches (alpha)

---

## PROJECTS

Projects are opt-in named workspaces that corral analysis runs into a shared directory. Commands with `--project <name>` or after `/project use <name>` write output to the project directory. Without a project, commands behave as before (timestamped dirs under `out/`).

```
/project create myapp --target /path/to/code -d "Description"
/project use myapp
/scan                          # output goes to project dir
/project status                # shows all runs
/project findings              # shows merged findings across runs
/project coverage              # shows tool coverage summary
/project report                # merged view across all runs
/project clean --keep 3        # delete old runs
/project none                  # clear active project
```

See `/project help` for full command list.

---

## DEFAULT TARGET DIRECTORY

When a command like `/scan`, `/agentic`, `/validate`, `/codeql`, or `/fuzz` is run **without a path argument**, resolve the default target in this order:

1. **Active project target:** the run lifecycle script reads the `.active` symlink to find the project target automatically
2. **Caller's directory:** if `$RAPTOR_CALLER_DIR` is set (launcher saves the user's cwd before switching to the RAPTOR repo dir), use it
3. **Ask the user** for the target path

Do not use the current working directory as a fallback — it is always the RAPTOR repo dir, not the user's target. Do not use any of these if the user already specified a path.

---

## RUN LIFECYCLE

When running any analysis command (`/scan`, `/validate`, `/understand`, `/codeql`, `/fuzz`, `/web`), use the run lifecycle stubs to create the output directory and track status:

**Before starting work:**
```bash
libexec/raptor-run-lifecycle start <command> --target <resolved_target> [--out <dir>]
```
Always pass `--target` with the resolved target path (see DEFAULT TARGET DIRECTORY for resolution order). Optionally pass `--out <dir>` to use a specific output directory. The last line of output is `OUTPUT_DIR=<path>` — use that path for all subsequent output files.

**After successful completion:**
```bash
libexec/raptor-run-lifecycle complete "$OUTPUT_DIR"
```

**On failure:**
```bash
libexec/raptor-run-lifecycle fail "$OUTPUT_DIR" "error description"
```

The `start` command automatically resolves the output directory using the active project (via `.active` symlink) or the default `out/` directory. Do not construct output paths manually.

**If `start` fails (non-zero exit):** STOP. Report the error to the user. Do not proceed with the command.

**Note:** `/validate` uses `libexec/raptor-validation-helper 0` instead of `raptor-run-lifecycle` — it bundles lifecycle management with inventory building.

Commands run via `python3 raptor.py` (scan, agentic, codeql, fuzz, web) manage lifecycle internally — do not call the stubs separately for those.

### Coverage tracking

The coverage tracking plugin (`plugins/coverage/`) tracks which source files the LLM reads during analysis via a PostToolUse hook. Loaded automatically by the launcher. Logs file paths to a manifest in the active run directory, converted to `coverage-record.json` when the run completes. Zero overhead when no run is active.

---

## SECURITY: UNTRUSTED REPOS

When scanning untrusted repositories:

- **Environment sanitisation**: `RaptorConfig.get_safe_env()` strips environment variables that tools may shell-evaluate (`TERMINAL`, `EDITOR`, `VISUAL`, `BROWSER`, `PAGER`). Always use `get_safe_env()` when spawning subprocesses.
- **File path injection**: Never interpolate file paths from scanned repos into shell command strings. Use list-based `subprocess` arguments.

---

## OUTPUT STYLE

**Status values:**
- In JSON: snake_case (`exploitable`, `confirmed`, `ruled_out`, `disproven`)
- In human-readable output (reports, terminal): Title Case (`Exploitable`, `Confirmed`, `Ruled Out`)
- Never ALL_CAPS (`EXPLOITABLE`, `CONFIRMED`, `RULED_OUT`)

**No red/green status indicators:**
- Do not use 🔴/🟢 - perspective-dependent (bad for defenders ≠ bad for researchers)
- Other emojis are fine (⚠️, ✓, etc.)

---

## CRASH ANALYSIS

The `/crash-analysis` command provides autonomous root-cause analysis for C/C++ crashes.

**Usage:** `/crash-analysis <bug-tracker-url> <git-repo-url>`

**Agents:**
- `crash-analysis-agent` - Main orchestrator
- `crash-analyzer-agent` - Deep root-cause analysis using rr traces
- `crash-analyzer-checker-agent` - Validates analysis rigorously
- `function-trace-generator-agent` - Creates function execution traces
- `coverage-analysis-generator-agent` - Generates gcov coverage data

**Skills** (in `.claude/skills/crash-analysis/`):
- `rr-debugger` - Deterministic record-replay debugging
- `function-tracing` - Function instrumentation with -finstrument-functions
- `gcov-coverage` - Code coverage collection
- `line-execution-checker` - Fast line execution queries

**Requirements:** rr, gcc/clang (with ASAN), gdb, gcov

---

## OSS FORENSICS

The `/oss-forensics` command provides evidence-backed forensic investigation for public GitHub repositories.

**Usage:** `/oss-forensics <prompt> [--max-followups 3] [--max-retries 3]`

**Agents:**
- `oss-forensics-agent` - Main orchestrator
- `oss-investigator-gh-archive-agent` - Queries GH Archive via BigQuery
- `oss-investigator-gh-api-agent` - Queries live GitHub API
- `oss-investigator-gh-recovery-agent` - Recovers deleted content (Wayback/commits)
- `oss-investigator-local-git-agent` - Analyzes cloned repos for dangling commits
- `oss-investigator-ioc-extractor-agent` - Extracts IOCs from vendor reports
- `oss-hypothesis-former-agent` - Forms evidence-backed hypotheses
- `oss-evidence-verifier-agent` - Verifies evidence via `store.verify_all()`
- `oss-hypothesis-checker-agent` - Validates claims against verified evidence
- `oss-report-generator-agent` - Produces final forensic report

**Skills** (in `.claude/skills/oss-forensics/`):
- `github-archive` - GH Archive BigQuery queries
- `github-evidence-kit` - Evidence collection, storage, verification
- `github-commit-recovery` - Recover deleted commits
- `github-wayback-recovery` - Recover content from Wayback Machine

**Requirements:** `GOOGLE_APPLICATION_CREDENTIALS` for BigQuery

**Output:** `.out/oss-forensics-<timestamp>/forensic-report.md`

---

## SOURCEHUNT

The `/sourcehunt` command runs a Clearwing-inspired per-file vulnerability hunting pipeline against a source repository.

**Usage:** `/sourcehunt <target_path> [--depth quick|standard|deep] [--budget <usd>] [--parallel <n>] [--sanitizer]`

**Pipeline:**
1. **Inventory** — enumerate all source files via `core/inventory`
2. **Tag** — classify each file: `memory_unsafe`, `parser`, `crypto`, `auth_boundary`, `syscall_entry`, `fuzzable`
3. **Rank** — score files: `surface×0.5 + influence×0.2 + reachability×0.3`
4. **Tier** — assign A/B/C (35/30/35 % of files; 70/25/5 % of budget)
5. **Hunt** — specialist LLM prompt per file class, parallel across tiers
6. **Verify** — ASan/UBSan crash-oracle upgrades evidence level to `crash_reproduced`

**Depth modes:**
- `quick` — fast band only, no sanitizer
- `standard` (default) — Tier A: standard band, Tier B/C: fast band
- `deep` — Tier A: deep band + sanitizer auto-enabled, Tier B: standard

**Specialist routing** (auto-selected by file tags):
- `memory_unsafe` → MEMORY_SAFETY hunter (overflows, UAF, double-free)
- `syscall_entry` → KERNEL_SYSCALL hunter (copy_from_user, IOCTL, locking)
- `crypto` → CRYPTO hunter (timing side-channels, nonce reuse, key lifecycle)
- `auth_boundary` → LOGIC_AUTH hunter (fail-open, comparison semantics, TOCTOU)
- `parser` → PARSER hunter (off-by-ones, sentinel collisions, truncation)
- default → WEB_FRAMEWORK hunter (injection, SSRF, authz bypass)

**Evidence ladder** (6 levels):
`suspicion` → `static_corroboration` → `crash_reproduced` → `root_cause_explained` → `exploit_demonstrated` → `patch_validated`

ASan/UBSan crash upgrades findings from `static_corroboration` → `crash_reproduced`, which gates PoC generation.

**Band promotion:** Files adjacent to `crash_reproduced` findings are automatically promoted to `deep` band.

**Findings pool:** Cross-agent shared state for primitive chaining (e.g. info_leak + arbitrary_write).

**Implementation:** `packages/sourcehunt/` + `raptor_sourcehunt.py`

**Output:** `out/sourcehunt_<timestamp>/sourcehunt_report.json` + `findings_pool.json` + `file_rankings.json`

**Pipeline integration:** Pass `--sarif <file>` to inject Semgrep hints into hunter prompts. Use `--out` to share directory with `/validate`.

---

## SOFTWARE COMPOSITION ANALYSIS (SCA)

The `/sca` command scans dependency manifests and queries the OSV database for known CVEs — inspired by Mythos-Router's supply-chain awareness.

**Usage:** `/sca <target_path> [--no-osv]`

**Supported:** `requirements.txt`, `package.json`, `pom.xml`, `Cargo.toml`, `go.mod`, `pyproject.toml`, `Gemfile`

**Pipeline:**
1. Discover manifest files in target repo
2. Parse each to extract `(name, version, ecosystem)` tuples
3. Batch-query `api.osv.dev/v1/querybatch` for CVEs (no API key required)
4. Report vulnerable packages with severity and CVE IDs

**Output:** `out/sca_<timestamp>/sca_report.json`

**Integration:** Run before `/sourcehunt` to identify vulnerable library code worth hunting. Combine with `/scan` for full SAST+SCA coverage.

---

## PLUGIN INTEGRITY

SHA-256 manifest generation and verification for RAPTOR plugins, skills, and MCP servers — supply-chain protection inspired by agent-supply-chain patterns.

**Usage:** `/plugin-integrity <command> <dir>`

**Commands:**
```bash
libexec/raptor-plugin-integrity generate        <dir>   # Generate INTEGRITY.json in <dir>
libexec/raptor-plugin-integrity verify          <dir>   # Verify <dir> against INTEGRITY.json; exit 2 on failure
libexec/raptor-plugin-integrity diff            <dir>   # Human-readable verification report
libexec/raptor-plugin-integrity promotion-check <dir>   # Full promotion gate (integrity + required files + pinned deps)
```

**When to use:**
- After reviewing a plugin — snapshot its state before promoting
- Before using a third-party MCP server or skill package
- In CI to verify plugin files weren't modified post-review
- Before running `/agentic` on a new plugin target

**Governance integration:** `packages/governance/` provides `GovernancePolicy`, `IntentClassifier`, `TrustScore`, and `AuditTrail` for agent safety enforcement. Use `@govern(policy)` decorator on tool functions.

**Browser security testing:** `packages/web/browser_agent.py` provides `run_full_scan(url)` for automated XSS/CSRF/auth-bypass/injection probing via browser-use (requires `pip install browser-use langchain-anthropic`).

---

## STRICT WRITE DISCIPLINE (SWD)

SHA-256 snapshot + drift detection for output artifacts — inspired by Mythos-Router's SWD verification protocol.

**Commands:**
```bash
libexec/raptor-swd snapshot <dir>   # Record baseline SHA-256 of all files
libexec/raptor-swd diff     <dir>   # Human-readable drift report
libexec/raptor-swd verify   <dir>   # Machine-readable JSON; exit 2 on drift
libexec/raptor-swd clean            # Remove all snapshots
```

**When to use:**
- Before/after `/patch` to verify patches applied correctly
- After `/sourcehunt` writes PoCs — confirm no accidental drift
- Integrity check: snapshot `out/<run>/` at start, verify at end

---

## ANALYTICS

Cross-session run statistics — inspired by Mythos-Router's Budget Analytics.

```bash
libexec/raptor-analytics show                   # All runs summary table
libexec/raptor-analytics show --project <name>  # Filter by project
libexec/raptor-analytics top                    # Findings by command type
```

Analytics are stored at `D:/tools/raptor-analytics.db` (SQLite). Record a run manually with `libexec/raptor-analytics record <out_dir>`.

---

## EXPLOITABILITY VALIDATION

The `/validate` command validates that vulnerability findings are real, reachable, and exploitable.

**Usage:** `/validate <target_path> [--vuln-type <type>] [--findings <file>]`

**Stages:** 0 → A → B → C → D → E → F → 1 (see `.claude/skills/exploitability-validation/PIPELINE.md`)

**Skills** (in `.claude/skills/exploitability-validation/`):
- `PIPELINE.md` - Stage naming convention (letters = LLM, numbers = mechanical)
- `SKILL.md` - Shared context, gates, execution rules
- `stage-0-inventory.md` through `stage-1-outputs.md` - Stage instructions

**Output:** `out/exploitability-validation-<timestamp>/validation-report.md`

**Pipeline handoff:** For `/understand` → `/validate` workflows, use the same `--out` directory so `context-map.json`, `checklist.json`, and `flow-trace-*.json` are shared automatically.

---

## CODE UNDERSTANDING

The `/understand` command provides deep, adversarial code comprehension for security research.

**Usage:** `/understand <target> [--map] [--trace <entry>] [--hunt <pattern>] [--teach <subject>] [--out <dir>]`

**Modes:**
- `--map` — Build context: entry points, trust boundaries, sinks → `context-map.json`
- `--trace <entry>` — Follow one data flow source → sink with full call chain → `flow-trace-<id>.json`
- `--hunt <pattern>` — Find all variants of a pattern across the codebase → `variants.json`
- `--teach <subject>` — Explain a framework, library, or pattern in depth (inline)

**Skills** (in `.claude/skills/code-understanding/`):
- `SKILL.md` — Gates, config, output format
- `map.md` — Entry point enumeration, trust boundary mapping, sink catalog
- `trace.md` — Step-by-step data flow tracing with branch coverage
- `hunt.md` — Structural, semantic, and root-cause variant analysis
- `teach.md` — Framework/pattern explanation with security conclusion

**Output:** Resolved by `libexec/raptor-run-lifecycle start understand` (project dir or `out/understand_<timestamp>/`)

**Pipeline integration:** `/validate` Stage 0 automatically imports `/understand` output via the bridge (`core/understand_bridge.py`). No `--out` alignment needed — the bridge searches: (1) co-located files, (2) project siblings, (3) global `out/` by target path + SHA-256 freshness. When found, it pre-populates `attack-surface.json`, imports flow traces as attack paths, and marks entry points/sinks as high-priority in the checklist.

---

## DIAGRAM GENERATION

The `/diagram` command generates Mermaid visual maps from `/understand` and `/validate` JSON outputs, giving researchers a visual representation of code flows, sources, sinks, trust boundaries, attack trees, and attack paths. Consider this 
very much a WIP but it could be of use for those wanting to see relationships and flows better. 

**Usage:** `/diagram <out-dir> [--target <name>] [--type context-map|flow-trace|attack-tree|attack-paths|all]`

**What gets rendered:**
- `context-map.json` → flowchart LR: entry points → trust boundaries → sinks; unchecked flows as dashed edges
- `attack-surface.json` → same layout (Stage B equivalent view)
- `flow-trace-*.json` → flowchart TD per trace: each hop in the call chain, tainted variables, branches, attacker control summary
- `attack-tree.json` → flowchart TD: knowledge graph nodes styled by status (confirmed/disproven/exploring/unexplored)
- `attack-paths.json` → flowchart TD per path: step chain with proximity score and blocker annotations

**Output:** `diagrams.md` written into the target directory (or `--stdout` to print)

**Implementation:** `libexec/raptor-render-diagrams <out-dir> [--target <name>]`

**When to run:** Diagrams are auto-generated at the end of `/validate` and `/understand --map`/`--trace`. Use `/diagram <dir>` to re-render after manual edits to JSON outputs.

---

## PROGRESSIVE LOADING

**When scan completes:** Load `tiers/analysis-guidance.md` (adversarial thinking)
**When validating exploitability:** Load `.claude/skills/exploitability-validation/SKILL.md` (gates, methodology)
**When validation errors occur:** Load `tiers/validation-recovery.md` (stage-specific recovery)
**When developing exploits:** Load `tiers/exploit-guidance.md` (constraints, techniques)
**When errors occur:** Load `tiers/recovery.md` (recovery protocol)
**When requested:** Load `tiers/personas/[name].md` (expert personas)
**When running /understand:** Load `.claude/skills/code-understanding/SKILL.md` (gates, config) plus the relevant mode file: `map.md`, `trace.md`, `hunt.md`, or `teach.md`
**When running /sourcehunt:** Load `.claude/skills/sourcehunt/SKILL.md` (pipeline, specialist routing, evidence ladder)
**When running /sca:** Load `.claude/skills/sca/SKILL.md` (manifest parsers, OSV API, output format)
**When running /corpus2skill:** Load `.claude/skills/corpus2skill/SKILL.md` (pipeline, loaders, hierarchy format)
**When running /understand or /validate (if corpus is available):** Load `packages/hacker_corpus/knowledge_base.py` auto-discover; if corpus is present, include relevant knowledge in analysis context via `get_hints(tags)`.

---

## BINARY ANALYSIS

**Flow: Find vulnerabilities FIRST, then check exploitability.**

1. **Analyze the binary** - Find vulnerabilities (buffer overflows, format strings, etc.)
2. **If vulnerabilities found** - Run exploit feasibility analysis (MANDATORY)

```python
from packages.exploit_feasibility.api import analyze_binary, format_analysis_summary

# MANDATORY: Run this after finding vulnerabilities
result = analyze_binary('/path/to/binary')
print(format_analysis_summary(result, verbose=True))
```

**DO NOT use checksec or readelf instead** - they miss critical constraints like:
- Empirical %n verification (glibc may block it)
- Null byte constraints from strcpy (can't write 64-bit addresses)
- ROP gadget quality (0 usable gadgets = no ROP chain)
- Input handler bad bytes
- Full RELRO blocks .fini_array too (not just GOT)

**The `exploitation_paths` section tells you if code execution is actually possible** given the system's mitigations (glibc version, RELRO, etc.).

**SMT integration (optional, requires `pip install z3-solver`):**

Two places Z3 is used — both degrade gracefully when absent:

1. **Binary / one-gadget** (`packages/exploit_feasibility/smt_onegadget.py`): checks
   whether a one-gadget's register/memory constraints are satisfiable given a crash
   state. Result in `exploitation_paths[vuln].one_gadget_info.smt_feasibility`.

2. **CodeQL dataflow** (`packages/codeql/smt_path_validator.py`): checks whether the
   branch conditions along a dataflow path are jointly satisfiable. `unsat` → false
   positive, skip LLM. `sat` → concrete input values fed into the LLM prompt and
   `DataflowValidation.prerequisites`. Best coverage: CWE-190, CWE-120/122,
   CWE-193, CWE-476.

---

## EXPLOIT DEVELOPMENT

**Verify constraints BEFORE attempting any technique.** Many hours are wasted on architecturally impossible approaches.

**MANDATORY: Check `exploitation_paths` verdict first:**
- Unlikely = no known path, suggest environment changes
- Difficult = primitives exist but hard to chain, be honest about challenges
- Likely exploitable = good chance, proceed with suggested techniques

**Follow the chain_breaks** - these tell you exactly what WON'T work.
**Follow the what_would_help** - these tell you what MIGHT work.

**ALWAYS offer next steps, even for Difficult/Unlikely verdicts:**
- Try alternative targets (if available)
- Focus on info leaks only
- Run in older environment (Docker)
- Move on to other targets

**Never just stop** - let the user decide how to proceed.

See `tiers/exploit-guidance.md` for detailed constraint tables and technique alternatives.

---

## HACKER CORPUS

The `/hacker-corpus` command fetches data from hacker community sources for corpus2skill ingestion.

**Usage:** `/hacker-corpus [--sources <list>] [--out <dir>] [--parallel] [--force]`

**Sources:** phrack, ghsa, capec, d3fend, oss_security, project_zero

**Default output:** D:/docs/hacker_corpus/

**After fetching:** Run `/corpus2skill --source D:/docs/hacker_corpus --name hacker_corpus` to build the skill hierarchy.

**Auto-injection:** The knowledge base is automatically loaded during `/sourcehunt` runs when corpus data is present at the default or configured path. No manual steps needed.

**Corpus path:** Default is `D:/docs/hacker_corpus/`. Override with `RAPTOR_CORPUS_DIR` env var.

**Skill hierarchy:** After running corpus2skill, the skill hierarchy at `.claude/skills/corpus/hacker_corpus/` is preferred over raw files for higher-quality hints.

---

## STRUCTURE

Python orchestrates everything. Claude shows results concisely.
Never circumvent Python execution flow.
- never disclose remote OLLAMA server location in code, comments, logs etc
- **Python path safety:** Never add anything to `sys.path` except `os.environ["RAPTOR_DIR"]`. Use the hard lookup (KeyError if unset) — no fallbacks, no `'.'`, no `os.getcwd()`, no hardcoded paths. The `libexec/` scripts handle their own path setup via `Path(__file__).resolve().parents[1]` and do not need `RAPTOR_DIR`.

---
name: sourcehunt
description: Clearwing-inspired per-file vulnerability hunting. Tags and ranks source files by attack surface, then dispatches specialist LLM hunters in parallel across A/B/C priority tiers with optional ASan/UBSan crash-oracle verification.
user-invocable: true
---

# SourceHunt Skill

Per-file vulnerability hunting pipeline inspired by Clearwing / Anthropic Glasswing.
Ranks source files by attack surface, routes each to a specialist LLM prompt, and
optionally verifies findings with ASan/UBSan crash oracles.

## When to Use

- Source code is C/C++/Rust/Python/Go and you want LLM-driven per-file hunting
- Static analysis (Semgrep/CodeQL) alone misses logic bugs and memory-safety issues
- You want crash-confirmed evidence before pursuing exploit development
- You need to prioritize which files deserve the deepest review

---

## Invocation

```
/sourcehunt <target_path> [options]
```

**Options:**
| Flag | Default | Description |
|------|---------|-------------|
| `--depth quick\|standard\|deep` | standard | Hunt depth (see below) |
| `--budget <usd>` | 5.0 | Total LLM cost cap |
| `--parallel <n>` | 4 | Concurrent file hunters |
| `--sanitizer` | off | Enable ASan/UBSan crash oracle |
| `--no-sanitizer` | — | Disable even with `--depth deep` |
| `--sarif <file>` | — | Inject Semgrep hints into prompts |
| `--max-files <n>` | 0 (all) | Limit files hunted |
| `--no-promotion` | — | Disable crash-neighbour promotion |

---

## Pipeline

```
Inventory → Tag → Rank → Tier A/B/C → Parallel Hunt → [ASan/UBSan] → Report
```

1. **Inventory** — enumerate source files via `core/inventory`
2. **Tag** — classify each file with security-relevant tags
3. **Rank** — score: `surface×0.5 + influence×0.2 + reachability×0.3`
4. **Tier** — A=top 35 % (70 % budget) / B=mid 30 % (25 %) / C=bottom 35 % (5 %)
5. **Hunt** — specialist LLM prompt per file class, parallel within each tier
6. **Verify** — ASan/UBSan crash upgrades evidence to `crash_reproduced`
7. **Promote** — files adjacent to crash-confirmed findings re-hunted at deep band

---

## File Tags → Specialist Routing

| Tag | Specialist | Focus |
|-----|-----------|-------|
| `syscall_entry` | KERNEL_SYSCALL | copy_from_user, IOCTL, locking discipline |
| `crypto` | CRYPTO | timing side-channels, nonce/IV reuse, key lifecycle |
| `auth_boundary` | LOGIC_AUTH | fail-open, comparison semantics, TOCTOU |
| `memory_unsafe` | MEMORY_SAFETY | overflows, UAF, double-free, integer truncation |
| `parser` | PARSER | off-by-ones, sentinel collisions, length truncation |
| (default) | WEB_FRAMEWORK | injection, SSRF, authz bypass, session handling |

---

## Evidence Ladder

```
suspicion → static_corroboration → crash_reproduced → root_cause_explained
         → exploit_demonstrated → patch_validated
```

ASan/UBSan crash upgrades `static_corroboration` → `crash_reproduced`.
`crash_reproduced` gates PoC generation in the `/validate` pipeline.

---

## Depth Modes

| Depth | Tier A band | Tier B band | Sanitizer |
|-------|------------|------------|-----------|
| quick | fast | fast | off |
| standard | standard | fast | off |
| deep | deep | standard | auto-on |

**fast** = truncated content (8K chars), 1 LLM pass  
**standard** = full specialist prompt (20K chars)  
**deep** = full prompt (40K chars) + sanitizer verification pass

---

## Execution

When `/sourcehunt` is invoked, run the lifecycle and then the Python pipeline:

```bash
libexec/raptor-run-lifecycle start sourcehunt --target <resolved_target>
# OUTPUT_DIR=<path>

python3 raptor_sourcehunt.py \
  --repo <target_path> \
  --depth <depth> \
  --budget <budget> \
  --parallel <parallel> \
  [--sanitizer] \
  [--sarif <sarif_file>] \
  --out "$OUTPUT_DIR"

libexec/raptor-run-lifecycle complete "$OUTPUT_DIR"
```

---

## Output Files

| File | Contents |
|------|---------|
| `file_rankings.json` | All files with scores, tags, tier assignments |
| `findings_pool.json` | All findings with evidence levels (cross-agent pool) |
| `sourcehunt_report.json` | Full pipeline summary + findings |

---

## Integration with Other Commands

- **After `/scan`**: Pass `--sarif out/<scan_dir>/combined.sarif` to inject Semgrep hints
- **Before `/validate`**: Use `--out` to share directory; findings_pool.json feeds Stage 0
- **After `/understand --map`**: Use context-map.json entry points as `entry_point` hints
- **With `/agentic`**: SourceHunt complements agentic by catching bugs Semgrep misses

---

## Findings Pool API (for chaining)

```python
from packages.sourcehunt import FindingsPool

pool = FindingsPool("out/sourcehunt_<ts>/findings_pool.json")
# Query primitives for exploit chaining
leaks = pool.get_by_primitive("info_leak")
writes = pool.get_by_primitive("arbitrary_write")
chains = pool.chain_candidates("info_leak", "arbitrary_write")
# Get only crash-confirmed findings
confirmed = pool.get_above_evidence("crash_reproduced")
```

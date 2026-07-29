# Work-Graph — endless multi-model orchestration

A durable **work-graph** that lets 3+ heterogeneous models/NNs (local Ollama /
Codex / Claude / Copilot) grind through a shared body of work — where a single
session's token/context budget never blocks progress.

Two modes the user asked for:
- **(a) Don't consume the session** → route cheap-tier tasks to **local Ollama**
  (no token/session billing).
- **(b) When a session *is* consumed, a new one runs** → an **external driver**
  spawns a fresh per-task session; it can't restart Claude itself (a documented
  hard limit), so autonomous restart is honest only for headless Ollama/Codex,
  while Claude stays human-gated.

Design spec: `docs/superpowers/specs/2026-07-29-graph-orchestration-design.md`.

## The one idea

**The graph is the program; sessions are disposable, crash-only workers.**
All durable state lives in the graph (SQLite/WAL, `raptor-worklog.db`). A worker
leases one task, does bounded work from its self-contained `spec`, writes a
result artifact + provenance, marks it done, and exits. Kill it `-9` mid-task and
nothing is lost — the lease expires and the task returns to `ready` for re-lease.
"Endless" is a property of *the graph + an external driver*, never of one session.

Three planes stay separated:

| Plane | What | LLM in loop? |
|---|---|---|
| **State** | the work-graph (single source of truth) | writes only |
| **Control** | deterministic scheduler over `depends_on` (ready-set) | **no** |
| **Verification** | different-provider check before `done` | yes, blind |

## Quick start — one command

The driver **auto-seeds** the graph from `claude-projects.json` on first run, so
there is no separate setup step. One command each:

```powershell
rp                    # interactive: pick a project → launch Claude (replaces ccr)
rp -Serve             # autonomous: auto-seed + drive local workers (drain then exit)
rp -Serve -Watch      # autonomous + resident PoC/debug monitoring (Ctrl-C to stop)
```

`rp -Serve` is exactly `raptor-worklog serve` (auto-seed included); pass
`--workers 3`, `--verify`, `--watch` through the CLI if you call it directly:

```powershell
py -3.11 libexec/raptor-worklog serve --workers 3          # 3 models at once
```

Individual commands (inspect / operate the graph directly — all optional):

```powershell
py -3.11 libexec/raptor-worklog list                      # whole graph
py -3.11 libexec/raptor-worklog ready  [--project P]       # runnable frontier
py -3.11 libexec/raptor-worklog next   [--project P]       # top task + routed model
py -3.11 libexec/raptor-worklog add --title T --spec "..." --capability triage
py -3.11 libexec/raptor-worklog compact --project P --show # bounded handoff (local NN)
py -3.11 libexec/raptor-worklog prune  --older-than-days 7 # retention (tombstone done)
py -3.11 libexec/raptor-worklog corpus --project P         # progress corpus INDEX.md
py -3.11 libexec/raptor-worklog seed                       # explicit (serve auto-seeds)
```

## The launcher `rp` (replaces `ccr`)

`ccr` (node-pty auto-injecting `/effort ultracode`) is retired. Its complexity
existed almost entirely to type one slash-command into the TUI, which spawned a
long tail of terminal/concatenation bugs. `rp` (`bin/rp.ps1`, pure PowerShell)
scans `C:\dev\projects\`, shows a resume-tagged menu, writes a ccr-compatible
`.raptor-session.json`, sets `RAPTOR_CALLER_DIR`, and launches **plain** `claude`
— no PTY, no `/effort` injection, no auto-rotate loop. Type `/effort` yourself in
the TUI if you ever want it (usually you won't).

## Capability routing (local-first)

The scheduler is deterministic (no LLM in the hot loop). Routing is a lookup
table (`packages/worklog/routing.py`):

| capability | local first | escalate |
|---|---|---|
| `scan` | deterministic tool | — |
| `triage` | ollama llama3.1 | — |
| `summarize` | ollama qwen2.5:14b (→ 72b heavy) | codex |
| `codegen` | ollama qwen2.5-coder:32b (→ 72b heavy) | codex → claude |
| `reason` | **claude (human-gated)** | — |
| `review`/verify | different provider than author | codex/copilot |

`on_prem_only` tasks are **structurally** confined to local models — a cloud
model can never lease them.

## Concurrency & memory

Multiple worker threads/processes coordinate purely through the graph
(blackboard/stigmergy). The **atomic lease** (`BEGIN IMMEDIATE` +
`UPDATE ... WHERE status='ready'`) guarantees no task is processed twice, so you
can run as many concurrent workers as your VRAM allows. Capability-diverse tasks
load different models simultaneously — that is how you "use more memory": e.g. a
`triage` (llama3.1), a `summarize` (qwen2.5:14b) and a `codegen`
(qwen2.5-coder:32b) run at once. VRAM is the real ceiling; Ollama evicts LRU
when models don't all fit.

## Bounded memory, retention & session-limit resilience

The whole point is developing **without stopping at a session limit**. Three simple
mechanisms keep memory bounded and work flowing:

- **Compaction** (`compact`) — a local NN compresses a project's state into a
  *fixed-volume* handoff (`--max-chars`), with a **deterministic hard cap** (the NN
  drafts, code enforces the budget). Replaces the ever-growing `その9→その8…`
  `next_plan` stack. The summarizer is a pluggable `str -> str` — swap in any
  existing-OSS summarizer; nothing here is bespoke.
- **Retention** (`prune`) — a finished task doesn't need its full ~10 KB spec kept
  forever, only the *fact* it finished, for a period. `prune --older-than-days N`
  tombstones old done tasks to a bounded marker.
- **Progress corpus** (`corpus`) — each project's progress is materialized as a small
  navigable `INDEX.md` (bounded handoff + open tasks + finished facts + artifact
  links), loaded **on resume** rather than carried in every session.
- **Route-around on limits** — if a worker hits a rate/quota/session limit, its task is
  *released* back to the graph (not failed) and that model is put on a cooldown; other
  models / a fresh cold invocation resume it. Local Ollama has no such limit, so
  cheap-tier work never stops. **Handoff, not residency**: `serve` drains autonomous
  work then exits cleanly — the durable graph is the handoff, and model reload is
  cheap, so no always-on daemon is required.

## Honest constraints (these are load-bearing, not caveats)

1. **Claude cannot self-restart / re-login.** The external driver owns restart
   authority and **halts at the auth gate** — it never loops past a re-login.
   "Endless" = an unbounded chain of *bounded* sessions with rare human auth gates.
2. **"Don't consume the session" is a *tiering* claim.** Local Ollama genuinely
   owns the cheap tier (triage/summarize/codegen-draft). **Real flagship reasoning
   still needs Claude** — a local model will not correctly execute a real 10 KB-
   context task. The win is: offload the cheap tier to local (free), chain bounded
   Claude sessions for the hard tier.
3. **The self-contained `spec` is the real crux, not storage.** The graph stops
   the `その9→その8…` *stacking* (history → `done` nodes), but each task's forward
   `spec` must still be authored to be self-contained. Treat "spec too big" as a
   risk to measure, not a solved problem.
4. **No machine exactly-once for irreversible effects.** git push / PyPI publish
   stay human-gated approval steps.

## Layout

```
packages/worklog/
  store.py       SQLite work-graph: schema, atomic lease, ready-set, TTL reclaim,
                 idempotent upsert, events, escalation signals
  validate.py    fail-closed invariants (acyclic deps, closed enums, cycle/topo,
                 provider/locality)
  routing.py     capability -> model routing (local-first, tag-tolerant)
  workers.py     adapters: Ollama (HTTP API, no session cost), Codex (headless
                 read-only), Claude (human-gated), Copilot (verify)
  driver.py      run_once (one tick) + serve (drain-then-exit) + parallel_serve (N workers)
                 + rate-limit route-around/cooldown
  seed.py        seed tasks from claude-projects.json
  compact.py     bounded-memory compaction (fixed-volume handoff summaries; pluggable)
  corpus.py      per-project progress corpus (navigable INDEX.md, load on resume)
  tests/         60 pytest cases (lease atomicity, idempotency, cycle, TTL reclaim,
                 verify gate, kill-and-resume, concurrency, auth-halt, rate-limit,
                 routing, seed, compaction/prune, corpus)
libexec/raptor-worklog   CLI (init|seed|add|list|ready|next|show|lease|done|fail|
                         reclaim|cycle-check|topo|run-once|serve|export|stats)
bin/rp.ps1 / rp.cmd / rp  the launcher (project picker + -Serve / -Next)
```

Run the tests: `py -3.11 -m pytest packages/worklog/tests/ -q`

# Work-Graph Orchestration — Design Spec (2026-07-29)

Status: **approved to build** (autonomous /goal, 10h). Author: Claude (Opus 5, ultracode).
Grounded in a 9-agent research workflow (`graph-engineering-research`, 807k tokens) + an
adversarial critique (F1–F7). This spec **adopts the critique's corrections** and states the
one place it deliberately diverges, with reason.

---

## 0. Goal (verbatim intent)

> 「3つ以上のモデル/NN が、セッションの消費(トークン/コンテキスト上限)に縛られず、
> エンドレスに作業を回せる構造」を **グラフエンジニアリング**で作る。
> 2モード:(a) **セッションを消費しない** = ローカル LLM をワーカーにする /
> (b) **消費しても新しいセッションが回る** = 外部ドライバが新セッションを起動する。

Seed: retire the fragile `ccr` launcher (node-pty auto-injecting `/effort ultracode`) and
replace it with a lightweight `rp` launcher, backed by a durable **work-graph**.

## 1. Core inversion

**The graph is the program; sessions are disposable, crash-only workers.** "Endless" is a
property of *the graph + an external driver*, never of any one session. All durable meaning
lives in the graph; a session holds only one task's working set. Three planes stay separated:

| Plane | What | LLM in loop? |
|---|---|---|
| **State** | the durable work-graph (single source of truth) | writes only |
| **Control** | deterministic scheduler over `depends_on` (ready-set) | **no** |
| **Verification** | different-provider check before `done` | yes, blind/parallel |

## 2. Honest constraints (these shape everything — no papering over)

1. **Claude cannot self-exit / self-restart / re-login** (`project_ccr_automation_limits`,
   `docs/CCR_AUTO_RESTART.md`). Restart authority lives in an **external, non-Claude driver**.
   "Endless" = an *unbounded chain of bounded sessions*, punctuated by rare **mandatory human
   auth gates**. No immortal session. The driver **halts at the auth gate** and never loops past it.
2. **Fragility removal is only for headless workers** (F3). The autonomous, no-node-pty path is
   `ollama` (local) + `codex exec` (headless). The **Claude worker stays node-pty + human-Enter
   gated** — honestly labeled, not pretended-autonomous.
3. **"Don't consume the session" is a *tiering* claim, not magic** (F1). Local Ollama can
   genuinely own the **cheap tier** (triage / classify / dedup / summarize / mechanical / draft),
   saving Claude budget. **Hard reasoning on real FullSense tasks still needs Claude** — a 14–32B
   local model will not correctly execute a real 10 KB-context raptor task. The win is: offload
   the cheap tier to local (free), chain bounded Claude sessions for the hard tier.
4. **The self-contained `spec` is the real crux, not storage** (F1). Today's `next_plan` strings
   are ~9–11 KB *because cold-start context genuinely is that big* (CLAUDE.md + 400-node memory KG
   + project familiarity). The graph compresses **history** (into `done` nodes, killing the
   `その9→その8…` stacking) but the **forward spec must still be authored and self-contained**.
   We treat "spec too big to be self-contained" as a **measured risk**, and the MVP acceptance
   test uses a **real** task, not a toy.
5. **No true exactly-once for LLM reasoning or irreversible remote effects.** Guarantee is: *a
   completed node's journaled output is immutable and never recomputed.* Irreversible effects
   (git push, PyPI publish) are **human-gated approval nodes** (never machine-exactly-once).
6. **Local-first (FullSense).** SQLite on local NVMe/NTFS; `on_prem_only` tasks are **structurally
   never leased by a cloud model**. Small local models are unreliable structured *writers* → they
   read/triage; larger models / Claude / Codex write graph mutations.

## 3. Storage decision — SQLite (WAL), minimal

One file `C:\dev\tools\raptor\raptor-worklog.db` = the work-graph store + queue + lease broker
+ small audit log, atomically consistent, zero-server, Python-3.11 stdlib (`sqlite3`), on local
NTFS. `claude-projects.json` + `SESSION_SUMMARY.md` become **generated projections/exports**.

**Deliberate divergence from the critique (F2/F4/F7).** The critique recommends *"extend the
existing `libexec/raptor-loop-queue` dir-queue; defer SQLite until a 2nd concurrent writer
exists."* That is correct **for a one-worker MVP** — but this goal's headline requirement is
**3+ concurrent heterogeneous workers**, so the second concurrent writer is a day-one target, not
a deferred bet. SQLite's `BEGIN IMMEDIATE` + conditional `UPDATE … WHERE status='ready'` is the
cleanest correct atomic lease for N workers and avoids a painful retrofit + the dir-queue's
TTL-reclaim / rename-race edge cases. We keep it **minimal** (adopting F7): **one `task` table +
one `event` audit table** — *not* the full 5-node/6-edge model, *not* content-addressed-artifact
storage, *not* an N-way quorum. JSON stays as a reversible export (`worklog-events.jsonl`,
git-trackable; the `.db` is untracked). We keep the dir-queue's proven ideas (crash-safe,
idempotent, UTF-8, exit-code discipline).

*Everything else from the critique is adopted as-is:* F1 (spec honesty + real-task acceptance),
F3 (fragility scope honesty), F5 (idle/stuck escalation), F6 (strip unverified citations/stats),
F7 (defer CAS/event-sourcing-elaborate/quorum-N).

## 4. Schema (minimal, fail-closed)

### `task` table
```
id            TEXT PRIMARY KEY         -- ULID-ish: YYYYMMDDTHHMMSS-<hex6> (sortable)
project       TEXT                     -- claude-projects.json key (fullsense/llive/…)
title         TEXT NOT NULL            -- 1-line
spec          TEXT NOT NULL            -- self-contained cold-start text (the crux, §2.4)
status        TEXT NOT NULL            -- pending|ready|leased|blocked|done|failed  (snake_case)
depends_on    TEXT                     -- JSON array of task ids (the DAG)
priority      INTEGER NOT NULL         -- smaller = higher (inherits project _priority rank)
capability    TEXT                     -- JSON array of tags: triage|summarize|codegen|reason|review|scan|web
on_prem_only  INTEGER NOT NULL DEFAULT 0
lease_owner   TEXT                     -- session id holding the lease
lease_expires REAL                     -- epoch seconds; NULL when not leased
attempt       INTEGER NOT NULL DEFAULT 0
result_ref    TEXT                     -- path/ref to the produced artifact (file), when done
result_by     TEXT                     -- model+session that produced it (provenance)
verified_by   TEXT                     -- session id of a DIFFERENT-provider verifier (nullable)
constraints   TEXT                     -- JSON array: no-push|read-only|needs-human-judgment|…
created_at    TEXT
updated_at    TEXT
```

### `event` table (append-only audit spine; folds to JSONL export)
```
seq        INTEGER PRIMARY KEY AUTOINCREMENT
ts         REAL
task_id    TEXT
kind       TEXT     -- created|ready|leased|lease_expired|done|failed|verified|blocked|escalated
by_model   TEXT
detail     TEXT     -- JSON
```

### Status machine
`pending` → (deps satisfied) `ready` → (atomic lease) `leased` → `done` | `failed`;
`leased` → `ready` on lease expiry (crash reclaim); any → `blocked` when a dep fails.

### Invariants (validator, fail-closed)
1. **Acyclic `depends_on`** — cycle-check on every proposed edge; reject fail-closed
   (a bad edge from a heterogeneous model could otherwise deadlock forever).
2. **Closed status/kind enums**, snake_case (raptor OUTPUT STYLE; no ALL_CAPS, no red/green).
3. **Lease exclusivity** — claim only via `UPDATE … WHERE status='ready' AND (lease_expires IS
   NULL OR lease_expires < now)` with rowcount==1 check inside `BEGIN IMMEDIATE`.
4. **Idempotent upsert** — re-adding same `id` with same content is a no-op (restart-safe).
5. **Local-first boundary** — `on_prem_only=1` task can never be leased by a cloud-model session.
6. **Verify-before-done (configurable)** — for autonomously-completed tasks, `done` may require a
   `verified_by` from a **different provider** than `result_by`. Default: **lenient for MVP**
   (single worker), strict when ≥2 providers configured (Phase 2 per open-Q).

## 5. Architecture

1. **Store (SQLite)** = system-of-record. Ready-set, `next_plan`, `SESSION_SUMMARY` are views.
2. **Scheduler (deterministic, no LLM)** — `ready = { tasks: every depends_on done, not leased }`
   ordered by `priority`. Handles the currently-linear per-project stacks trivially and is
   DAG-ready without over-building (F4: we ship priority-ordered ready-set; genuine multi-parent
   fan-out is exercised only when real tasks need it).
3. **Worker = crash-only lease** — LEASE one ready task (atomic) → do bounded work → write result
   + provenance → mark `done` → exit. Crash/exhaustion → lease TTL expires → task returns `ready`
   → re-leased. At-least-once + idempotent = effectively-once. `taskkill -9` is lossless.
4. **External driver (`rp --serve`, non-Claude)** owns restart: watch graph → ensure a live worker
   for the top ready task → reclaim expired leases → **escalate to human** when *runnable work
   exists but ready-set is empty for N ticks* or *a task fails twice* (F5 — the real endless-idle
   failure mode) → **halt at auth gate**.
5. **Heterogeneous routing, local-first** (deterministic table; learned router deferred):

   | capability tag | first choice (local) | escalate to |
   |---|---|---|
   | scan / mechanical | deterministic tool (Semgrep/OSV), no LLM | — |
   | triage / classify / dedup / tag | ollama llama3.1 (fast) | — |
   | summarize / extract | ollama qwen2.5:14b | codex |
   | codegen / patch draft | ollama qwen2.5-coder:32b | codex → claude |
   | deep reason / plan | **claude** (human-gated) | — |
   | review / verify | **different provider than author** | codex/copilot |

6. **Coordination = blackboard/stigmergy** — workers touch only the graph; no agent-to-agent
   channel (matches raptor "main is sole 司令塔"). Adding a model = another poller. Two nested
   context-reset levels: intra-session Workflow subagents (fresh context) inside one leased task;
   cross-session worker rotation is the outer loop.

## 6. `rp` launcher (entry point)

Replaces the node-pty `/effort ultracode` injector. **The project-picker MVP is already built and
verified** (`bin/rp.ps1` + `rp.cmd` + `rp`): pure PowerShell, scans `C:\dev\projects\`, resume
tags, writes ccr-compatible `.raptor-session.json`, sets `RAPTOR_CALLER_DIR`, launches plain
`claude` (no PTY, no effort injection). Modes:

- `rp` / `rp -Project <p>` — **human entry**: pick project → (graph-wired) lease its top ready task
  → launch a worker pointed at that one task's self-contained `spec`. Injects "here is your next
  ready node," not a blind mode string. Claude path stays node-pty + human-Enter (honest, §2.2).
- `rp -Serve` — **the external driver loop** (the honest home of "endless"): drives headless
  ollama/codex workers, respawns fresh sessions, escalates idle/stuck, halts at auth.

## 7. Components (build order)

```
packages/worklog/
  __init__.py
  store.py       # SQLite store: schema, atomic lease, ready-set, TTL reclaim, idempotent upsert, events
  validate.py    # fail-closed invariants (acyclic deps, enums, lease, on_prem, verify-gate)
  schedule.py    # ready-set computation + idle/stuck escalation signals (F5)
  routing.py     # capability -> worker tier table (local-first)
  workers.py     # adapters: ollama (local), codex (headless), claude (interactive/human), copilot (verify)
  driver.py      # rp --serve loop: lease -> dispatch -> commit -> reclaim -> escalate -> halt@auth
  seed.py        # seed tasks from claude-projects.json (next_plan->spec, _priority->priority, plan_ref->ref)
  events.py      # JSONL export (git-trackable audit)
libexec/raptor-worklog   # CLI: init|seed|add|list|ready|lease|done|fail|show|cycle-check|export|serve|stats
bin/rp.ps1               # (built) picker; extend: -Serve + task-launch
packages/worklog/tests/  # pytest: lease atomicity, idempotency, ready-set, cycle, TTL reclaim, routing, seed
```

## 8. Phasing

- **MVP (this session):** SQLite store + validator + scheduler + CLI + seed-from-json + ollama &
  codex headless workers + `rp --serve` driver + tests. **Acceptance = kill-and-resume on a REAL
  task**: lease a real task → `taskkill -9` the worker mid-run → a fresh worker re-leases from the
  graph alone → completes → `done`. Plus: local ollama processes a cheap-tier task end-to-end
  (proving "don't consume the session").
- **Phase 2:** strict different-provider verify gate; git-tracked JSONL export in CI; Windows Task
  Scheduler wiring for the driver.
- **Phase 3:** learned local router (trained on `attempt` log); migrate the 400-node memory KG in
  as a bitemporal tier; N-way quorum; saga/outbox for irreversible effects.

## 9. Open questions — decided autonomously (per /goal), stated for course-correction

1. Day-one autonomous workers = **ollama + codex headless** (core to "don't consume session");
   Claude = interactive human-gated escalation.
2. SSOT boundary = **reference, don't subsume**. Work-graph is a new layer; `claude-projects.json`
   stays as seed/export; the 400-node `memory/` KG stays independent (referenced via `plan_ref`).
3. Task authoring = **both**: seed from `claude-projects.json` now; CLI `add` lets a planning
   session emit tasks.
4. DB = `C:\dev\tools\raptor\raptor-worklog.db` (untracked) + `worklog-events.jsonl` export.
5. Verify gate = **mechanism built, lenient default for MVP**, strict when ≥2 providers.
6. External driver = **build the `rp -Serve` loop now**; Task Scheduler wiring documented, not required.

## 10. Sources — honesty note (F6)

The synthesis cited several arXiv IDs (2605.03310, 2603.01548, 2605.06365, 2605.00827) and
statistics (41–87%, 93%) that are **not verifiable and are dropped** per the user's two-pillar +
`feedback_benchmark_honest_disclosure` rules. **None of the design decisions depend on them** —
deterministic scheduling, crash-only workers, atomic leasing, and de-correlated verification stand
on first principles (Candea & Fox *Crash-Only Software*, HotOS 2003; SQLite WAL + `BEGIN
IMMEDIATE`; classic blackboard architecture). The real multi-agent failure taxonomy anchor, if
one is wanted, is **MAST (Cemri et al., arXiv 2503.13657)** — to be verified against primary
source before it informs any code.
```

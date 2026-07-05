# Parity measurement pipeline (executed 2026-07-05)

The skill's `parity-eval.md` describes the A/B methodology; this file is the
**runnable, executed** version, and records the key methodological decisions.

## The two axes, and which one is measurable

1. **Objective correctness** (deterministic keys). Measured twice
   (`run-baseline-capture.js`, `run-stageA-opusraw.js`): **opus-raw 18/18 — CEILING.**
   Opus 4.8 solves these single-pass, so there is NO Opus→Fable gap to measure and
   NO room for scaffold uplift here. Don't keep probing this axis.

2. **Single-pass quality** (depth / coverage / subtle-correctness on open-ended tasks,
   NO objective key). This is the axis where an Opus↔Fable gap *could* appear, so it is
   where the parity question is actually testable. Measured by the pipeline below.

## Pipeline (quality axis)

**Generate** (`run-qualcap.js` over `qual-tasks.jsonl`): 3 arms per task —
`opus-raw`, `fable-raw`, `opus+deep-reason` (with external verify). Returns full answers,
NO in-workflow grading (grading by an Opus arm would be self-correlated).

**Judge** (`judge_qualcap.py` → `bin/ext_judge.py`): for each task, the 3 answers are
**deterministically shuffled** to anonymous labels A/B/C (rotation by task index → removes
fixed position bias, reproducible), then an **independent, non-Anthropic judge — OpenAI
Codex / gpt-5.4 — ranks them blind** on correctness/depth/coverage. Codex is independent
of BOTH Opus and Fable, so the verdict is not self-graded (the methodology's core
requirement). Rankings are mapped back to models and tallied.

**Aggregate**: win counts per arm + pairwise (scaffold-vs-opus-raw, fable-vs-opus-raw,
scaffold-vs-fable). Frozen to `qual-parity-<date>/{results.json,report.md}`.

## Perishability — the one thing to get right before Fable access ends

**Only the `fable-raw` arm is perishable.** `opus-raw` and `opus+deep-reason` are
repeatable forever. So the priority while Fable is available is to **freeze fable-raw on
as many quality-discriminating tasks as possible, cheaply** (`run-fableonly.js` over
`qual2-tasks.jsonl` = 1 agent/task). The opus-raw + scaffold arms and the blind judging
can be added later against the frozen Fable answers — the judge (codex) is repeatable.

## Reusable artifacts

- `bin/ext_verify.py` / `ext_verify_batch.py` — non-Opus refute-by-default claim verifier
  (single / batched). Backends: codex (authenticated), gemini/copilot (auth-gated).
- `bin/ext_judge.py` — non-Anthropic **blind quality judge** (ranks anonymized answers).
  Validated: on a controlled 3-answer case it ranked correct-and-deep > terse-correct >
  wrong, with accurate reasons.
- `gen_qualcap.py` / `gen_qual2.py` — quality task generators. `qual-tasks.jsonl` (5,
  3-arm) + `qual2-tasks.jsonl` (10, fable-frozen).
- `judge_qualcap.py` — shuffle → blind-judge → aggregate → freeze.

## Honesty

Small-N, single blind judge, single run per arm → **indicative, not statistically
powered**. Report exactly what the counts say; never state "measured parity" beyond that.
A quality ranking is softer than an objective key. The independent (non-Anthropic) judge
is the one thing that makes the verdict trustworthy rather than self-graded.

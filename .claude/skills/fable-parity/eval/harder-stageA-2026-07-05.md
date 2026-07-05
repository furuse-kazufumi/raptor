# Harder eval — Stage A (opus-raw discriminator) — 2026-07-05

**Goal:** find objective, single-context, no-tool reasoning tasks that opus-raw
(Opus 4.8, single pass) actually FAILS — the only place a scaffold could measurably
close a gap. Staged so the expensive scaffold/Fable arm (Stage B) runs ONLY on
tasks opus-raw fails.

**Method:** 9 harder tasks (`harder-tasks.jsonl`, computed keys via `gen_harder_tasks.py`,
brute-force / theory-checked), opus-raw single pass + Opus grader vs key. 18 agents.

## Result: opus-raw 9 / 9 — CEILING AGAIN. `opus_raw_failed = []`.

| task | category | opus-raw |
|---|---|---|
| h1  | 60-symbol DFA trace, count a state | PASS |
| h2  | multi-bug debugging (vowel counter) | PASS |
| h3  | 4-set inclusion-exclusion (<1000, primes 2/3/5/7) | PASS |
| h6  | nonlinear mod recurrence to a(50) | PASS |
| h8  | Wythoff game — who wins from (13,20) | PASS |
| h9  | count length-30 binary strings avoiding '101' (DP) | PASS |
| h10 | CRT over 3 moduli, smallest x | PASS |
| h11 | lattice paths avoiding a point | PASS |
| h12 | exact hypergeometric probability | PASS |

Combined with the 2026-07-05 baseline (9/9) this is **18/18** for opus-raw across two
escalating rounds. **No Stage B was run — there is no discriminating subset.**

## Honest conclusion

I could not manufacture an objective, single-context, no-tool reasoning task in this
difficulty band that Opus 4.8 fails single-pass. Therefore **scaffold uplift on this
task class is unmeasurable — not because the scaffold is weak, but because the baseline
is already at ceiling** (matches the skill's own theory: don't scaffold what the base
model already solves).

Where opus-raw *does* fail — and thus where fable-parity's value actually lives — is
NOT this class:
- **Tool/retrieval-required tasks** — a knowledge gap, fixed by `research-synthesize`
  (tools), not by more reasoning passes. Not a single-pass *reasoning* failure.
- **Open-ended judgment with no objective key** — cannot be graded this way; the
  generation–verification gap is unfavorable (verifier as wrong as generator).
- **Genuinely frontier/novel problems** beyond an author's ability to write with a
  computed key.

The measurable value that DID appear this session is on the **reliability / independent-
verification** axis, not the raw-uplift axis: `plan-verify` caught a load-bearing
assumption that the Opus verifier had CONFIRMED but the independent non-Opus family
(codex) REFUTED with specific evidence — a correlated-blind-spot catch an Opus-only
pipeline would have shipped. That is the honest, demonstrated payoff.

**Recommendation:** stop trying to prove reasoning-uplift on objective probes (two
ceilings is enough signal). Invest the scaffold where it demonstrably pays: independent
(non-Opus) verification of load-bearing claims/assumptions, tool-grounded research, and
long/among-many-sources synthesis — not single-pass arithmetic/logic Opus already nails.

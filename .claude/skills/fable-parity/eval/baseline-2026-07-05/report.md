# fable-parity baseline capture — 2026-07-05

Perishable Fable baseline on frontier-discriminating hard tasks (computed keys). Captured while Fable access was live; the Fable arm cannot be regenerated after access ends.

## Tally (correct / available / total)

| arm | correct | available | total |
|---|---|---|---|
| opus-raw | 9 | 9 | 9 |
| fable-raw | 9 | 9 | 9 |
| opus+deep-reason | 8 | 9 | 9 |

## Per-task correctness

| task | category | opus-raw | fable-raw | opus+deep-reason |
|---|---|---|---|---|
| h01 | long-horizon | PASS | PASS | PASS |
| h03 | deductive-reasoning | PASS | PASS | PASS |
| h04 | long-horizon | PASS | PASS | PASS |
| h05 | multi-constraint-planning | PASS | PASS | PASS |
| h06 | estimation | PASS | PASS | PASS |
| h07 | deductive-reasoning | PASS | PASS | PASS |
| h08 | long-horizon | PASS | PASS | PASS |
| h09 | deductive-reasoning | PASS | PASS | PASS |
| h10 | debugging | PASS | PASS | fail |

## Discrimination (tasks where opus-raw FAILED)

**opus-raw passed everything → CEILING again on this set.** No gap to measure here; the hard set still isn't hard enough for opus-raw. Harder/frontier tasks needed. (This is an honest negative result, not a failure of the harness.)

## Honest interpretation (read before drawing conclusions)

Two load-bearing findings, both negative for the "scaffold buys uplift here" thesis:

1. **No measurable Opus→Fable gap on this class.** opus-raw 9/9 = Fable-raw 9/9. Even on
   frontier-discriminating hard tasks (30-step DFA traces, 3^777 mod 1000, tribonacci
   counts to length 24, a(20) recurrences, unique-solution logic grids, 3-bug sieves),
   Opus 4.8 is already at ceiling. The perishable Fable baseline therefore shows **Fable
   does not out-solve Opus on this task class** — so fable-parity's value is *not* here.
   To find a real gap you need tasks where opus-raw actually fails: longer horizons, tasks
   requiring tool use / retrieval, genuinely open-ended judgment, or multi-hour chains.

2. **The scaffold LOST a point it should have won (8/9 < 9/9), and the cause was an
   orchestration bug, not a reasoning gap.** On h10 (3-bug debugging), opus-raw and
   fable-raw both found all three bugs; `opus+deep-reason` returned the literal string
   **`"test"`** (confidence "high"). Root cause: deep-reason's synthesis agent emitted a
   degenerate-but-schema-valid object `{answer:"test", confidence:"high", confidence_note:"test"}`,
   and the workflow had no content guard, so it shipped. This is exactly the
   `usage-on-opus.md §6` failure mode (self-critique/synthesis can flip a right answer to
   wrong) made concrete: **adding orchestration added a failure surface on a task the base
   model already solved.**
   - **Fix applied (2026-07-05):** `deep-reason.js` now discards a synthesis answer that is
     implausibly short (<40 chars) when real attempts existed (≥120 chars) and falls back to
     the best-verified attempt. Mirrored to the global skill copy. (Not yet re-run to confirm
     the fallback recovers h10 — re-run `run-baseline-capture.js` to verify, or resume
     `wf_bb777bac-63e` from the synthesis step.)

**Bottom line:** on objective, single-context, no-tool hard reasoning, Opus 4.8 needs no
scaffold and the scaffold can only break even or lose. fable-parity's real payoff must be
sought where a single Opus pass genuinely fails — verification-heavy research (tool-grounded),
very long horizons, or where an *independent non-Opus verifier* catches errors a lone Opus
misses. That is the next eval to build, not more of these.

Single run per arm, no repeats -> indicative. Grader is a single Opus judge vs an explicit computed key. fable-raw depends on the harness provisioning a real Fable subagent (check the model field). Full answers included for freezing the Fable baseline.

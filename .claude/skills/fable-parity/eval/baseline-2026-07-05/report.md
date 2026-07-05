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

Single run per arm, no repeats -> indicative. Grader is a single Opus judge vs an explicit computed key. fable-raw depends on the harness provisioning a real Fable subagent (check the model field). Full answers included for freezing the Fable baseline.

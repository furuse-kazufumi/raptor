# Quality parity — blind independent judge — 2026-07-05

5 quality-discriminating open-ended tasks. 3 arms (opus-raw, fable-raw, opus+deep-reason+ext). A blind, independent **codex (gpt-5.4)** judge ranked the anonymized answers per task (non-Anthropic → independent of both Opus and Fable). Fable answers frozen here are perishable.

## Wins (ranked #1 by the blind judge)

- **fable-raw**: 2 / 5
- **opus-raw**: 0 / 5
- **opus+deep-reason**: 3 / 5

## Pairwise (out of tasks judged)

- opus+deep-reason ranked ABOVE opus-raw: 4 / 5  (does the scaffold improve on a raw Opus pass?)
- fable-raw ranked ABOVE opus-raw: 3 / 5  (is there an Opus→Fable single-pass quality gap at all?)
- opus+deep-reason ranked ABOVE fable-raw: 3 / 5  (does the scaffold reach/exceed Fable?)

## Per task

| task | archetype | judge ranking (best→worst) | winner |
|---|---|---|---|
| q1 | code-design | fable-raw > opus-raw > opus+deep-reason | **fable-raw** |
| q2 | adversarial-spec | fable-raw > opus+deep-reason > opus-raw | **fable-raw** |
| q3 | hard-analysis | opus+deep-reason > opus-raw > fable-raw | **opus+deep-reason** |
| q4 | debugging-reasoning | opus+deep-reason > opus-raw > fable-raw | **opus+deep-reason** |
| q5 | systems-tradeoff | opus+deep-reason > fable-raw > opus-raw | **opus+deep-reason** |

## Honest caveats

- Single blind judge (codex), single run per arm, N=5 → INDICATIVE, not statistically powered. A quality ranking is softer than an objective key; codex is one family's judgment.
- This measures single-pass QUALITY (depth/coverage/subtle-correctness), the axis where an Opus↔Fable gap could appear (objective correctness was at ceiling for both — see harder-stageA). Do NOT report 'measured parity' beyond exactly what these counts say.

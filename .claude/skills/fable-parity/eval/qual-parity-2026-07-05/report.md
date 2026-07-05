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

## Interpretation (the pattern matters more than the totals)

This is the FIRST eval this session with real structure (objective probes were at
ceiling). Do not read it as "scaffold reaches parity" — read the per-task pattern:

- **Raw Opus single-pass is never best (0/5).** On open-ended quality, both Fable and
  the scaffold beat a raw Opus pass more often than not. So a single-pass quality gap
  over raw Opus is real.
- **Fable wins on breadth/design tasks, loses on analytical ones.** Fable won q1
  (code-design) and q2 (adversarial-spec) — tasks rewarding one coherent, wide, well-
  organized pass — but ranked LAST on q3 (hard-analysis) and q4 (debugging), where
  getting subtle technical distinctions exactly right matters. Fable does NOT dominate.
- **The scaffold wins where verification asymmetry is favorable, and can REGRESS where
  it isn't.** opus+deep-reason won q3/q4/q5 (analysis, debugging, systems-tradeoff —
  checkable subtleties, where decompose→verify→synthesize pays) but came DEAD LAST on
  q1 (code-design), BELOW even raw Opus. Concrete honest finding: on a wide design task,
  the synthesis/graft step can lose the coherence a single long deep pass produces — the
  scaffold is not free and is not uniformly better. This matches the skill's own theory
  (scaffold helps when checking is cheaper than producing; hurts on coherence-heavy
  breadth tasks with weak verification asymmetry).

**Honest bottom line:** "Does Opus+scaffold reach Fable-quality?" is **task-dependent** —
it exceeds Fable on analytical/verification-favorable tasks and underperforms both Fable
AND raw Opus on at least one design task. There is NO uniform parity claim to make; the
scaffold should be ROUTED to analytical tasks and kept OFF coherence-heavy design ones.

## Honest caveats

- Single blind judge (codex), single run per arm, N=5 → INDICATIVE, not statistically powered. A quality ranking is softer than an objective key; codex is one family's judgment.
- This measures single-pass QUALITY (depth/coverage/subtle-correctness), the axis where an Opus↔Fable gap could appear (objective correctness was at ceiling for both — see harder-stageA). Do NOT report 'measured parity' beyond exactly what these counts say.

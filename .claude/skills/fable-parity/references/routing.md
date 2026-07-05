# Routing: which scaffold (if any) to spend on

This is the decision guide for `fable-parity`. It answers two questions in order:

1. **Should I scaffold at all**, or just answer directly? (Most tasks: answer directly.)
2. **If yes, which of the six workflows** fits this task shape — and how to chain them.

The whole skill rests on one lever: the **generation–verification gap**. Spending
orchestration only pays off when *checking or selecting* a good answer is cheaper than
*producing* one. Where that asymmetry is wide (and, better, where a real external
checker exists — tests, a symbolic validator, an executor, retrievable sources), test-time
compute buys a lot. Where checking is as hard as solving, every scaffold below degenerates
toward the base rate and you have spent tokens for nothing. Route accordingly.

> **Honest status.** These workflows are designed to close the Fable→Opus per-pass gap on
> principled grounds (test-time compute + independent verification). This skill does **not**
> ship with a measured parity benchmark, and nothing here should be read as a proven parity
> result. To actually measure whether a scaffold reached parity on your task class, see
> `eval/parity-eval.md`. Never report parity that was not measured.

---

## Gate 0 — is this worth the orchestration overhead?

**Default is: answer directly.** Orchestration multiplies token cost and (for the
parallel workflows) wall-clock. Only cross the gate when the task clears *all three*:

1. **Stakes** — being wrong is expensive (ships to a user, drives a decision, hard to undo,
   or feeds later steps that compound the error). A throwaway or easily-corrected answer is not worth it.
2. **Single-pass risk** — a first, direct pass would plausibly be *shallow or error-prone*:
   a long dependent derivation, a wide solution space, a claim-heavy assertion, a
   far-horizon plan. If a direct pass is obviously adequate, stop here.
3. **A usable asymmetry exists** — you can check/select/refute candidates *more cheaply than
   you can generate them* (tests, a validator, retrievable citations, or at minimum an
   independent adversarial re-read on clean context). If verification is as hard as the task
   itself, scaffolding will not help — see "When the uplift does not apply" below.

**Answer directly (do NOT trigger a workflow) when the task is:**

- Trivial / mechanical / lookup: `ls`-grade edits, a known file change, a definition, a
  one-line factual recall you're confident of, arithmetic you can just do.
- Short and self-evidently checkable at a glance (the answer *is* its own proof).
- Purely a knowledge/fact gap. Sampling and voting add **zero information** — if the base
  model doesn't know it and can't derive it, every attempt is wrong the same way. The fix is
  retrieval/tools, not orchestration. (`research-synthesize` is the exception *only* because
  it actually retrieves.)

Rule of thumb: reach for the **cheapest** adequate move first. Per-token capability ordering,
cheapest first: direct answer < a single `adversarial-verify` pass (you already have a draft to
check) < `deep-reason` < heavier decomposition/research < heavy multi-candidate planning. Note
that `deep-reason` — even at low `attempts` — is **not** free self-consistency: on top of
sampling N attempts it also decomposes the problem and adversarially verifies *each* attempt
before synthesis, so it is strictly heavier than bare sample-and-vote and sits above a lone
`adversarial-verify` pass, not below it. Escalate structure only after the cheap move is shown
to be insufficient — do not open with the heaviest workflow.

---

## Gate 1 — which workflow?

Route by the *shape of the task* and *what you already have in hand*.

| You have / the task is… | Workflow | Invoke with | Why this one |
|---|---|---|---|
| A single hard question, derivation, proof, or analysis where one pass drops intermediates or takes a shortcut | **deep-reason** | `{ task, context?, attempts? }` (default `attempts: 3`) | Decompose → N *diverse independent* attempts in parallel → adversarially verify each → synthesize the strongest sub-parts. Recovers **depth of multi-step reasoning** by turning one long deep chain into many short, verified hops. |
| A **draft answer/finding you're about to ship** and want it self-checked first | **adversarial-verify** | `{ answer?, claims?, context?, voters? }` (default `voters: 3`) | Extracts load-bearing claims, spawns independent skeptics prompted to **refute** (default-refuted if uncertain), majority-votes, returns survivors + refuted-with-reasons + a corrected answer. Recovers **catching one's own errors** — the reviewer runs on clean, un-anchored context so it doesn't inherit the draft's blind spot. |
| A **claim-heavy or citation-heavy** assertion (API names, file paths, facts, numbers) you're about to state confidently | **adversarial-verify** | `{ claims: [...], context? }` | Same machinery, aimed at **calibration**: independent skeptics try to **refute** each claim (default-refuted when uncertain), majority-vote, and return the **surviving** claims vs the **refuted** ones — each refutation with its reason — plus a corrected answer, hunting fabricated specifics before they ship. |
| An open **research / survey / prior-art / "what exists"** question where breadth and citations matter | **research-synthesize** | `{ question, depth? }` (`quick` \| `standard` \| `deep`, default `standard`) | Multi-modal search fan-out (each agent searches a *different way*) → dedup → deep-read top sources → completeness-critic loop → cited synthesis. Recovers **research thoroughness** *and* fills genuine knowledge gaps via retrieval. |
| You need to **enumerate alternatives / approaches** to a hard problem before committing (wide solution space, first-mode risk) | **deep-reason** (internal) · **plan-critique** (if the artifact is a plan) · **research-synthesize** (only if the options must come from outside) | `{ task, attempts }` / `{ goal }` / `{ question, depth }` | The exploration is **generative, not retrieval**. `deep-reason`'s N *diverse independent* attempts **are** the divergent sampling of the solution space — different framings produced in parallel, then adversarially verified and grafted; no external checker or corpus is needed to invent internal/conceptual approaches. If the artifact you want is a *plan*, use `plan-critique` instead — its N candidate plans (different framings) play the same divergent role. Reach for `research-synthesize` **only** when the alternatives must come from the *outside world* — surveying **prior art** or **existing approaches** you cannot generate from what the model already knows — because only then is external search-fan-out the point. |
| A **design or implementation plan** where the solution space is wide and a first-draft plan would miss angles, ordering, or prerequisites | **plan-critique** | `{ goal, constraints?, candidates? }` (default `candidates: 3`) | N diverse candidate plans (different framings) → judge panel scores on multiple lenses → synthesize the winner grafting runners-up's best ideas → adversarial risk/pre-mortem pass. Recovers **planning horizon** by externalizing the plan and stress-testing it before execution. |
| An open **research / prior-art** question whose **answer you will act on**, where cited-but-unverified is not enough | **research-verify** | `{ question, depth?, voters?, max_claims? }` (default `voters: 2`) | Runs `research-synthesize`, then extracts the load-bearing claims and has independent skeptics **refute** each against **primary/independent** sources, returning every claim graded CONFIRMED / REFUTED / UNCERTAIN with a corrected answer. Recovers **research thoroughness + calibration** — the packaged composition of `research-synthesize` and `adversarial-verify`. |
| A **plan you will actually execute** whose success rides on assumptions that could be wrong (a feature/API exists, an operation is reversible, a dependency/version/limit is as believed) | **plan-verify** | `{ goal, constraints?, candidates?, voters?, max_assumptions? }` (default `voters: 2`) | Runs `plan-critique`, then extracts the plan's load-bearing **assumptions** and has independent skeptics **refute** each against primary/independent evidence — refuted → blocker/plan change, uncertain → an early 'validate-before-starting' step. Recovers **planning horizon + external grounding** — the packaged composition of `plan-critique` and `adversarial-verify`, catching false assumptions the internal pre-mortem shares. |

Disambiguation, since three of these can "generate N and pick":

- **Goal is an answer to a hard problem →** `deep-reason`.
- **Goal is a plan/design →** `plan-critique`.
- **Goal is breadth + citations from the outside world →** `research-synthesize`.
- **Goal is research you'll act on, where each claim must be verified (not just cited) →** `research-verify` (`research-synthesize` + `adversarial-verify`, packaged).
- **Goal is a plan you'll execute where a wrong assumption is expensive →** `plan-verify` (`plan-critique` + `adversarial-verify`, packaged — grounds the plan's assumptions in evidence).
- **Goal is to not ship a wrong thing you already drafted →** `adversarial-verify`.

---

## Chaining — the common compositions

Workflows compose. The high-value chains:

- **Ship gate (almost always): `<anything>` → `adversarial-verify`.**
  Any answer produced by `deep-reason`, `research-synthesize`, or `plan-critique` — or by a
  plain direct pass on a high-stakes task — should pass through `adversarial-verify` before
  you present it as final. It is the cheapest independent check and directly targets confident
  wrong answers. Feed it the prior output's `answer`/`claims`.

- **Plan then execute deeply: `plan-critique` → `deep-reason` per step.**
  Use `plan-critique` to produce a vetted, ordered plan, then run `deep-reason` on each hard
  step whose result later steps depend on. This front-loads the reasoning into a low-ambiguity
  plan so per-step execution stays inside per-pass competence. (Trivial steps just get done
  directly — don't `deep-reason` a one-liner.)

- **Research you'll act on: use `research-verify` directly.**
  It packages `research-synthesize` → load-bearing-claim extraction → `adversarial-verify` as one
  workflow, returning each claim graded against primary/independent sources. Reach for it instead
  of hand-chaining the two when the research output will drive a decision — the verify pass is what
  catches a plausible-but-wrong finding that a cited-only synthesis would present as settled.

- **A plan you'll execute: use `plan-verify` directly.**
  It packages `plan-critique` → assumption-extraction → `adversarial-verify` as one workflow,
  grounding the plan's load-bearing assumptions in primary evidence before you commit. Reach for
  it over plain `plan-critique` when a false assumption (a feature that doesn't exist, an
  irreversible step believed reversible) would be costly — `plan-critique`'s internal pre-mortem
  cannot catch an assumption the planner *believes*, because it shares that belief.

- **Research then reason: `research-synthesize` → `deep-reason`.**
  When the hard problem needs facts the model doesn't reliably have, retrieve first (this fills
  the knowledge gap that pure sampling cannot), then reason over the cited context by passing
  the synthesis in as `deep-reason`'s `context`.

- **Research then plan: `research-synthesize` → `plan-critique`.**
  Survey prior art / options, then feed the findings as `constraints`/context into planning so
  candidate plans start from what's known rather than reinventing it.

- **Full stack for a big deliverable:**
  `research-synthesize` → `plan-critique` → (`deep-reason` per hard step) → `adversarial-verify`
  on the assembled result. Use this only when Gate 0 stakes clearly justify it.

Design note: the terminal check should be **independent** of whatever produced the artifact —
a verifier that shares the generator's context inherits its blind spot, and correlated errors
survive the vote. That is why `adversarial-verify` runs its skeptics on clean context, and why
the *parity verdict itself* (see `eval/parity-eval.md`) must be signed off by a non-Fable judge
rather than by the model that produced the output.

---

## Cost & latency caveats

- **Everything here costs linearly-to-superlinearly more tokens.** `deep-reason` is roughly
  `attempts` × generation + verification; `adversarial-verify` is ~`voters` × claims + a
  synthesis; `research-synthesize` scales with `depth` (search fan-out + deep reads + critic
  loop); `plan-critique` is ~`candidates` × plan-generation + a judge panel + a risk pass.
  Chains multiply. Price a method **per token, not per problem**, and keep `attempts`/`voters`/
  `candidates` at their small defaults (3) unless you have evidence more helps — voting and
  candidate gains **plateau** and do not scale indefinitely.
- **Wall-clock vs. tokens differ.** The fan-out workflows dispatch parallel agents, so
  wall-clock can stay reasonable even as token spend climbs — but each parallel branch is real
  spend. `depth: "deep"` and long chains dominate latency.
- **Self-consistency is the honest baseline and it is hard to beat.** Raising `attempts`/
  `voters` on `deep-reason`/`adversarial-verify` is usually a better spend than reaching for a
  heavier chain. Don't stack structure you can't justify.
- **The verifier is the product, not the sample count.** A weak or hackable checker caps the
  gain and gets Goodharted (proxy reward rises while true quality falls). Invest in a genuinely
  independent check (executable tests, a validator, diverse/adversarial critics) before buying
  more attempts.
- **On the hardest problems, "weak model + compute" may cost more than just escalating.**
  Matching a stronger model via many attempts or deep chains can burn more tokens and
  wall-clock than calling the stronger model once. When Gate 0's asymmetry is thin and stakes
  are high, prefer escalation to Opus over piling on scaffolds (this is the parity-gated
  escalation path — degrade gracefully rather than ship sub-Opus output).

---

## When the uplift does not apply (route to something else)

If the task is any of these, no workflow above will manufacture the missing capability —
recognize it at Gate 0 and switch strategy:

- **Missing knowledge / facts** the model can't derive → retrieval/tools. Only
  `research-synthesize` helps, and only because it actually retrieves.
- **Below the coverage floor** — the correct answer never appears in the model's sample
  distribution at feasible N. Re-ranking and pruning can't create it. Escalate the model or
  change the approach.
- **Verification-hard tasks with no asymmetry** (hard proofs, open-ended judgment, novel
  claims with no ground truth) — the verifier is as wrong as the generator; the whole scheme
  degenerates to base rate.
- **Systematic, correlated errors / miscalibration** — shared-weight samples share blind
  spots, so confident wrong answers *win* the majority vote. Diversity (different framings,
  genuinely adversarial roles, ideally a different model family for the judge) matters far more
  than raw count; orchestration cannot remove a bias uniform across the ensemble.
- **A genuinely novel reasoning step / capability jump** the model can't do in one pass —
  rearranging passes it *can* do won't produce a lemma or algorithm it lacks.
- **True long-horizon coherence** — decomposition mitigates but per-step error compounds
  geometrically with depth, and the planner is itself a weak-model bottleneck. Keep chains
  short and checkpointed; escalate rather than lengthen.

In all of these, prefer retrieval, tools, or escalation to a stronger model over spending more
orchestration — and say so honestly rather than presenting a scaffolded result as if it closed
a gap it did not.

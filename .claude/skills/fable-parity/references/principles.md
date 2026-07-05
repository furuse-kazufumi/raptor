# fable-parity — Principles

*Why spending orchestration on Opus can recover Fable-level output — and where it provably cannot.*

This is the theory file. It states the mechanism the skill bets on, maps each recovery technique to the Fable-inline behavior it buys back, and draws a hard line around what orchestration does **not** recover. It makes **no** claim of measured parity — see `eval/parity-eval.md` for how to actually measure the gap. Read this before trusting any workflow in this skill to "close the gap."

---

## 1. The thesis

A stronger model (Fable 5, Mythos-class) mostly out-produces a weaker one (Opus) by doing more *inside a single forward pass*: it sustains a longer chain of dependent inferences, self-checks mid-generation, and enumerates more alternatives before committing. That per-pass advantage is largely **variance and depth that can be re-manufactured with test-time compute** — decompose the task, run diverse independent attempts, verify them adversarially, and synthesize the survivor. The Workflow tool is the vehicle; this skill packages the recipes.

The bet is principled, not benchmarked. It rests on one asymmetry (below) that is real but bounded. Where the asymmetry holds, orchestration buys a lot; where it collapses, the scaffold degenerates to Opus's own base rate and you have spent tokens for nothing. Treat every "recovers" claim here as *conditional on that asymmetry existing for your task*.

---

## 2. The master lever: the generation–verification gap

Every technique that reliably lifts a weaker model routes through **one** asymmetry: *checking or selecting a good answer must be easier than producing one.* When it holds — unit tests, a symbolic validator, an executor, a genuinely independent critic — test-time compute converts *coverage* (the model can sometimes reach the answer) into *accuracy* (it reliably returns that answer). When checking is as hard as solving, the verifier is as wrong as the generator and the whole scheme degrades to the base rate.

Two consequences shape the entire skill:

- **Coverage and selection are separate bottlenecks.** Sampling raises coverage (pass@k) roughly log-linearly (Large Language Monkeys, Brown 2024), but you only *cash it in* with a selector strong enough to pick the winner. With no verifier, majority vote and reward models plateau after a few hundred samples. Fan-out without a selector is wasted money.
- **The verifier is the product.** A weak or hackable checker caps the gain and gets Goodharted under best-of-N — gold reward eventually *falls* as the proxy reward rises (Gao 2022). Investing in the checker (executable tests, symbolic validators, diverse juries, adversarial falsifiers) beats buying more samples. This is why the skill's `adversarial-verify` workflow prompts skeptics to *refute* and defaults-to-refuted under uncertainty, rather than asking a friendly critic "does this look right?"

**Honest baseline.** Plain CoT + self-consistency is hard to beat per token. Debate, Reflexion, and Tree-of-Thought frequently *lose* to it at matched budget (per budget-matched evaluations reported around 2024). Always price a method **per token, not per problem**, and reach for heavy structure only after the cheap methods are exhausted.

---

## 3. Technique → Fable-inline behavior → cost → workflow

The Fable-inline behaviors below are the concrete per-pass advantages this skill tries to reconstruct (from the gap map). Each row is grounded in the literature cited; the "buys back" claim is only valid under the generation–verification asymmetry of §2.

### Cost-ascending ladder (reach top-down)

| # | Technique | Rough capability-per-token | Primary workflow |
|---|-----------|----------------------------|------------------|
| 1 | CoT + self-consistency (majority vote) | cheapest, honest baseline | `deep-reason` |
| 2 | Best-of-N + a cheap **hard** verifier | best when a real checker exists | `deep-reason`; **`plan-critique`** (best-of-N over *plans*) |
| 3 | Task decomposition (least-to-most) | good, if decomposition is correct | `research-synthesize` (secondary aid) |
| 4 | LLM-as-judge jury (panel selection) | cheap selector, decorrelates bias | `adversarial-verify`, **`plan-critique`** |
| 5 | Reflexion / self-critique **with external feedback** | strong *only* with grounded signal | `plan-critique` (final-stage tail only) |
| 6 | Tree / Graph of Thought | high cost; needs cheap state eval | *not shipped — aspirational (see note)* |
| 7 | Multi-agent debate | worst per token; modest, inconsistent | `adversarial-verify` (as critique, not consensus) |

### Per-technique detail

**Self-consistency (majority vote over sampled CoT).**
- *Mechanism:* Sample N chains at temperature; return the modal final answer. Correct derivations converge; errors are idiosyncratic and diffuse, so the mode concentrates on the most independently-supported answer.
- *Buys back (Fable-inline):* *Catching one's own variance* — the arithmetic slips and unlucky path choices Fable avoids by self-correcting mid-pass. Pushes accuracy toward Opus's own pass@k ceiling on tasks it *can* solve but does inconsistently. Buys reliability, **not new capability**.
- *Cost / caveat:* Linear N× tokens (5–40 typical; saturates ~40). Requires a discrete extractable answer — **cannot vote over free-form prose**.
- *Evidence:* Wang et al. 2022; budget-matched evaluations (~2024) finding CoT+SC beats debate/Reflexion at matched budget; Brown 2024 (voting plateaus after a few hundred samples).
- *Workflow:* `deep-reason`.

**Best-of-N with a verifier / reward model (selector).**
- *Mechanism:* Sample N candidates, score each with an **external** checker (tests, symbolic validator, outcome/process reward model), return the argmax. The sampler explores; the verifier exploits.
- *Buys back (Fable-inline):* *Knowing which of its own outputs is best.* This is the single highest-leverage recovery **when a trustworthy verifier exists** — a weaker model with a real checker reaches or exceeds a much larger one on problems it can already sometimes solve.
- *Cost / caveat:* N× generation + verifier cost. **The verifier is the risk:** a weak verifier caps the gain and gets Goodharted (best-of-N over-optimizes a proxy until gold reward drops).
- *Evidence:* Cobbe 2021 (GSM8K verifiers); Lightman 2023 (process reward, "Let's Verify Step by Step"); Snell 2024 (small model + PRM search beats 14× larger on easy/medium MATH, **not** the hardest); Large Language Monkeys (SWE-bench 15.9%→56% *with executable tests*); Gao 2022 (reward-model over-optimization).
- *Workflow:* `deep-reason` (grafts the strongest verified sub-parts at synthesis); **also `plan-critique`, which runs best-of-N over candidate *plans*** before jury selection.

**Task decomposition (least-to-most / plan-then-solve).**
- *Mechanism:* Split a hard problem into an ordered sequence/DAG of easier subproblems, feeding sub-answers forward. Each sub-call stays inside the model's per-pass competence.
- *Buys back (Fable-inline):* *Depth of multi-step reasoning* — the 8–12+ dependent steps Fable holds in one pass. Decompose-and-checkpoint turns one long deep chain into many short reload-from-context hops, so the next step *reads* a verified prior result instead of re-deriving it in-pass.
- *Cost / caveat:* Multiple calls; the decomposition itself must be correct or **errors propagate and compound geometrically with depth**. The decomposer is a weak-model bottleneck.
- *Evidence:* Zhou et al. 2022 (least-to-most; large jumps on compositional generalization); Khot 2022 (decomposed prompting); Kambhampati LLM-Modulo (LLMs weak stand-alone planners, useful *inside* a decomposed loop with an external checker).
- *Workflow:* `research-synthesize` (sub-question split is a **secondary** aid there — its defining axis is multi-modal *search* fan-out with external retrieval, not decomposition), and the decompose step of `deep-reason`.

**Reflexion / self-critique loops.**
- *Mechanism:* Generate → obtain feedback → verbally reflect on what went wrong → retry, carrying the reflection as episodic memory. Turns a feedback signal into an in-context "gradient" with no weight update.
- *Buys back (Fable-inline):* *Within-session learning from a failed attempt* — the iterative debugging Fable does when it notices a contradiction and revises. **Only** when the feedback is external and grounded (tests, env reward, compiler/tool errors).
- *Cost / caveat:* Multiple rounds; gains are entirely contingent on feedback quality. **Pure intrinsic self-critique commonly does nothing or actively hurts** — it flips right answers to wrong.
- *Evidence:* Shinn 2023 (91% pass@1 HumanEval *with unit-test feedback*); Madaan 2023 (Self-Refine). **Counter:** Huang et al. 2023 ("LLMs Cannot Self-Correct Reasoning Yet" — internal-only self-correction lowers GSM8K accuracy); FlipFlop (models cave when merely challenged).
- *Workflow:* `plan-critique` — **as the final-stage tail only** (the pre-mortem / dependency-check pass that runs *after* best-of-N plan generation and jury selection), using that pass as the "external" grounding; never intrinsic-only.

**Adversarial verification / prover–verifier games.**
- *Mechanism:* Pair a candidate with a dedicated falsifier whose only job is to find a flaw; accept only survivors. Exploits verification asymmetry and forces legible, checkable output.
- *Buys back (Fable-inline):* *Catching one's own errors* and *calibration* — Fable's mid-pass "wait, that doesn't follow" and its instinct to hedge unverified specifics. Makes even a **weak** checker useful, because catching one specific flaw is easier than solving.
- *Cost / caveat:* Extra generation for the adversary, plus the design cost of a **genuinely independent** falsifier. If the critic is the same model in the same context with the same blind spots, the gain collapses. The critic must run in fresh, un-anchored context.
- *Evidence:* Irving et al. 2018 (debate, theory); Kirchner et al. 2024 (OpenAI prover–verifier games — a weak verifier's acceptance constrains a stronger prover, improving legibility). Recent work also suggests the generation–verification gap is real but often needs training to fully materialize, rather than coming free at inference.
- *Workflow:* `adversarial-verify`.

**LLM-as-judge juries (panel of evaluators).**
- *Mechanism:* Replace one judge with a panel of **diverse** models scoring independently, then aggregate (mean/vote). Diversity decorrelates individual biases and cuts variance.
- *Buys back (Fable-inline):* *Selection precision without a frontier judge* — a better, cheaper selector to plug into best-of-N and the parity verdict, with less self-preference / position / verbosity bias.
- *Cost / caveat:* N judge calls, but small models → often net cheaper than one big judge. **Does not fix biases shared across the panel** (similar training data → correlated failure); some multi-agent-judge setups *amplify* bias.
- *Evidence:* Verga et al. 2024 (PoLL: panel of 3 small models correlates with humans better than a single GPT-4 judge, ~7× cheaper, less intra-model bias). Caveat: recent work suggests some multi-agent-judge setups amplify rather than cancel shared bias.
- *Workflow:* `adversarial-verify` (majority over independent skeptics) and `plan-critique` (the judge panel that scores candidate plans). Note the standing rule: **a Fable-produced result may not be judged "at parity" by Fable itself** — the parity verdict needs an independent (non-Fable) judge.

**Tree / Graph of Thought.**
- *Mechanism:* Make the search over reasoning states explicit — branch, self-evaluate each state, expand/prune/backtrack (ToT) or merge partial results (GoT). Adds deliberate search + lookahead on top of linear CoT.
- *Buys back (Fable-inline):* *Breadth of exploration and planning* — Fable's habit of enumerating non-obvious approaches and recovering from a wrong early step instead of doubling down.
- *Cost / caveat:* Very high — branching × depth × per-state evaluation, often 10–100× a single CoT. **Works only when partial states are cheaply self-evaluable;** if the model can't score partial progress, the search is blind, and token cost rarely beats best-of-N.
- *Evidence:* Yao 2023 (Game of 24: 4% CoT → 74% ToT); Besta 2023 (GoT). Skeptic: dramatic on puzzle/search tasks with clear state evaluation, marginal elsewhere.
- *Workflow:* **not implemented by shipped `deep-reason`** — the shipped workflow runs N *independent* best-of-N attempts, **not** sequential branch/prune/backtrack search. Kept here only as an aspirational extension for tasks with a cheap state heuristic.

**Multi-agent debate.**
- *Mechanism:* Several instances answer, then over R rounds read each other's answers and revise toward consensus.
- *Buys back (Fable-inline):* Some factuality/reasoning correction when an alternative derivation dislodges a wrong path — but **weakly and inconsistently.**
- *Cost / caveat:* Highest cost here — N agents × R rounds × growing context → near-quadratic token blowup, typically the worst accuracy-per-token. Convergence often just reproduces the most-confident view; shared weights mean shared blind spots (correlated errors).
- *Evidence:* Du et al. 2023 (positive on factuality/math). **Rebuttals:** budget-matched evaluations (~2024); recent work also suggests debate gains scale poorly, and that single-agent setups can match or beat multi-agent ones under equal thinking-token budgets.
- *Workflow:* Used in `adversarial-verify` **only as one-shot independent critique, not as multi-round consensus** — the consensus dynamic is what fails per token.

### Orchestrator–worker (the substrate, not a depth technique)

A planner decomposes, dispatches parallel/specialized workers, and aggregates. It **recovers breadth, throughput, and context management** on large multi-part tasks (long research, multi-file code) by keeping each worker in-competence — it adds **no reasoning depth by itself**, and the orchestrator is a single point of failure (bad plan → wrong tree; workers conflict at merge). This is the machinery `research-synthesize` and the parallel fan-out ride on, not a source of parity on its own. (Anthropic multi-agent research system; Kim 2023 LLM Compiler; Kambhampati LLM-Modulo — "LLM proposes, external verifier disposes.")

---

## 4. How the six workflows embody this

- **`deep-reason`** — self-consistency + best-of-N-with-verifier over **N diverse independent attempts** (not tree/graph search). Recovers *reasoning depth* and *variance-driven slips* by running those attempts in parallel, adversarially verifying each, and grafting the strongest verified sub-parts. (Tree/Graph-of-Thought is an aspirational extension the shipped workflow does **not** implement — no sequential branch/prune/backtrack.)
- **`adversarial-verify`** — prover–verifier games + diverse juries (+ debate as one-shot critique only). Recovers *error-catching* and *calibration* by extracting load-bearing claims and spawning independent skeptics prompted to refute, defaulting-to-refuted under uncertainty.
- **`research-synthesize`** — multi-modal **search** fan-out + orchestrator-worker with external retrieval. Recovers *research thoroughness* and *breadth* by fanning out agents that each search a **different way** (broad web / recent / authoritative-primary / contrarian-failure / adjacent-domain), deduping, deep-reading, then running a completeness critic loop before a cited synthesis. Sub-question decomposition is a secondary aid, not the defining axis — external retrieval and search-method diversity are.
- **`research-verify`** — `research-synthesize` + `adversarial-verify`, composed and packaged. Recovers *research thoroughness AND calibration*: it runs the search-fan-out synthesis, then extracts the load-bearing claims and has independent skeptics refute each against primary/independent sources (default-refuted under uncertainty), returning every claim graded CONFIRMED/REFUTED/UNCERTAIN with a corrected answer. This is the generation–verification gap applied to research findings — use it over a cited-only synthesis whenever the answer will be acted on.
- **`plan-critique`** — best-of-N candidate **plans** + LLM-as-judge jury selection + synthesis-by-grafting, with a final adversarial pre-mortem as the **tail**. Recovers *planning horizon* by generating N diverse candidate plans under different framings, scoring each with a judge panel across multiple lenses, grafting the best ideas of the runners-up into the winning plan, then adversarially checking ordering, prerequisites, and "what breaks 5 steps in" (pre-mortem / dependency check — externally grounded, never intrinsic-only) before execution.
- **`plan-verify`** — `plan-critique` + `adversarial-verify`, composed. Recovers *planning horizon AND external grounding*: it runs plan-critique, then extracts the plan's load-bearing **assumptions** and has independent skeptics refute each against primary/independent evidence, folding refuted assumptions into plan changes and uncertain ones into early validate-first steps. This is the generation–verification gap applied to what a plan *takes for granted* — the one thing plan-critique's internal pre-mortem structurally cannot catch, because the pre-mortem shares the planner's belief in its own assumptions.

---

## 5. What this does NOT recover

Orchestration re-ranks, prunes, and re-manufactures depth from passes the model *can already perform*. It creates no capability the base model lacks. Do not deploy a scaffold against any of the following expecting parity — it will burn tokens and return the base rate, often with false confidence.

- **Missing knowledge and facts.** Sampling and voting add zero information. If Opus doesn't know a fact and can't derive it, every sample is wrong the same way and the majority is confidently wrong. The fix is retrieval/tools, not more compute. (This is why the skill injects context — `rad-research` / search — rather than expecting latent recall.)
- **Anything below the coverage floor.** If the correct answer is not in the model's sample distribution (pass@k ≈ 0 at feasible N), no selector, judge, or debate can surface it. Orchestration prunes; it does not create.
- **Verification-hard tasks with no asymmetry.** Hard proofs, open-ended judgment, novel claims with no ground truth — when checking is as hard as solving, verifiers and juries are as wrong as the generator and the scheme degenerates to the base rate. **A task with no verifiable sub-structure is out of scope for this skill.**
- **Systematic, correlated errors and miscalibration.** Shared weights share blind spots, so confident wrong answers *win* majority votes and juries *amplify* uniform bias rather than cancel it. Diversity (different families, genuinely adversarial roles) matters far more than raw count — and even that cannot remove a bias uniform across the ensemble.
- **Genuinely novel reasoning steps / capability jumps.** A step Opus cannot perform in one pass (an unlearned algorithm, a required lemma it can't derive) is not recovered by rearranging passes it *can* perform. Decomposition helps only when the sub-steps are individually in-reach.
- **True long-horizon coherence.** Decomposition mitigates but per-step error compounds geometrically with depth; long plans still drift, and the orchestrator's own planning is a weak-model bottleneck (LLM-Modulo).
- **Raw single-pass creativity.** The spontaneous, in-one-breath generation of a non-obvious framing is not reconstructed by fan-out-then-select. Forced fan-out (optionally seeded by TRIZ / cross-domain ideation) widens the candidate set and a selector picks the best of *what was generated* — it cannot conjure a mode the sampler never emitted.
- **Latency.** Every workflow here trades wall-clock for quality: N parallel attempts still incur dispatch/merge rounds, verification passes are serial after generation, and critic loops add turns. Parity-by-orchestration is slower than a single Fable pass, sometimes by a large factor.
- **Dollar / token cost.** Matching a stronger model via 40–250 samples or deep trees frequently costs **more** in tokens and wall-clock than just calling the stronger model. "Weak + compute = strong" is often *not* the cheaper trade at the frontier (Snell 2024). Small-model-plus-compute matches a bigger model only in a band — easy-to-medium difficulty where coverage is non-zero **and** verification is cheap. On the hardest problems the bigger model wins and extra compute does not close the gap.
- **Calibrated self-knowledge.** Intrinsic self-critique can't reliably tell when it's right, so it is no substitute for an external oracle; without one, self-refinement can regress *below* the first attempt.

---

## 6. Honesty note

This skill is **designed** to close the Opus/Fable gap on principled grounds (test-time compute + verification). It does **not** ship with a proven parity benchmark, and nothing here should be read as a measured result. Any "reaches parity" assertion must clear an independent (non-Fable) judge and cite fresh verification evidence per the completion gate — see `eval/parity-eval.md` for the A/B harness, eval dimensions, judge-calibration threshold, and the rule to **report where parity fails rather than average it away**. When in doubt, state the uncertainty; never claim measured parity that was not measured.

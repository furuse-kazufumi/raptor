# Parity Eval — how to actually measure whether Opus + fable-parity approaches Fable

> Read this section before you quote any number from this skill.

## 0. Honesty rule (non-negotiable, read first)

**`fable-parity` does NOT ship with a proven parity benchmark.** It is designed on
*principled* grounds — the generation/verification asymmetry plus test-time compute —
and those grounds are strong enough to justify building it. They are **not** evidence
that it works. No measurement has been run. Nobody has demonstrated that
`Opus + fable-parity` reaches `Fable-raw` on any task.

So the design argument (see `references/principles.md`) is a **hypothesis**, and this
file is the **only** thing that is allowed to turn it into a claim. Concretely:

- **Never state measured parity that was not measured.** "This should approach Fable"
  is a design claim; "on the probe set, blind judges preferred `Opus+fable-parity`
  over `Opus-raw` in X% of tasks, closing Y% of the Fable gap" is a measured claim.
  They are different sentences and must never be blurred.
- Any "we reached parity" assertion is a completion claim and is bound by the **Iron
  Law** of `superpowers:verification-before-completion`: *no completion claim without
  fresh verification-command evidence.* The evidence here is a run of this harness on
  `eval/probe-tasks.jsonl`, with the judge outputs saved. No run → no claim.
- This mirrors the user's standing discipline: `feedback_benchmark_honest_disclosure`
  ("異常に良い結果は内訳を疑う / 失敗を消さず教訓に残す"),
  `feedback_verify_existence_before_claiming`, and `feedback_no_solo_ai_judgment`.
- **The most likely honest outcome is partial.** The research says orchestration
  recovers *reliability and breadth*, not *new capability*. Expect gains on some
  categories, flat on verification-hard ones, and be suspicious of a clean sweep
  (a clean sweep usually means the judge is biased or the tasks are too easy — see §5).

If you only read one section, read this one, then §6.

---

## 1. What "parity" means here

Parity is a **differential** question, not an absolute-correctness one:

> On Opus-tier-shaped tasks, does the output of **Opus + fable-parity** approach the
> output of **Fable-raw** — measurably closer than **Opus-raw** gets on its own —
> and at an overhead we are willing to pay?

This is deliberately comparative. Existing tooling (`doublecheck`, GSD `ai-evals`,
`superpowers:verification-before-completion`) answers "is this output correct/verified?".
None of them answers "does this output match what the stronger model would have
produced?" — that A/B gap is what this harness adds.

Parity is measured **per category**, never as a single blended headline. A method can
close the gap on multi-step reasoning while doing nothing on calibration; averaging
those together hides exactly the information a reviewer needs.

---

## 2. The three arms

Every probe task is answered three times, by three arms:

| Arm | Model | Scaffold | Role in the comparison |
|---|---|---|---|
| `fable-raw` | Fable 5 (Mythos-class) | none — single natural pass | **Upper reference / ceiling.** The quality we are trying to approach. |
| `opus-raw` | Opus | none — single natural pass | **Baseline / floor.** What Opus does with no help. The thing we must beat. |
| `opus+fable-parity` | Opus | routed through the `fable-parity` workflow for the task's category | **System under test.** Opus spending orchestration instead of depth. |

Fixed across arms (so the only variables are model + scaffold):

- **Same task set** — `eval/probe-tasks.jsonl`, verbatim, for all three arms.
- **Same input context** — identical prompt, attachments, and tool access. If the
  parity arm is allowed retrieval/tools, the raw arms get the same allowance, or the
  comparison silently rewards tool access rather than orchestration.
- **Identity hidden from judges** — no arm label ever reaches the judge (see §3).
- **One arm = one config.** Do not tune `opus+fable-parity` against the same probe
  tasks you then report on; that is training on the test set. Split: tune on a dev
  slice, report on a held-out slice, or freeze the config before the reporting run.

Note the direction of the delta: here the *reference* model (Fable) is **stronger**
than the *baseline* (Opus). `opus+fable-parity` is trying to climb toward the ceiling,
not defend it. A result where the parity arm **exceeds** `fable-raw` is possible but
should be treated as a red flag for judge bias or too-easy tasks, not celebrated (§5).

---

## 3. Protocol

### 3.1 Task set

Read tasks from `eval/probe-tasks.jsonl`. Each line is one task; the harness relies on
these fields (keep them stable so this eval and the probe file stay coherent):

```
{ "id": "...", "category": "<one of the 8 task categories below>",
  "prompt": "...", "rubric": "known-correct answer + grading key for this task" }
```

- `id` — stable task identifier (`p01`…).
- `category` — one of the eight labels in the routing table below. It selects which
  `fable-parity` workflow the parity arm routes through, and is the axis all metrics are
  reported over.
- `prompt` — the task text, fed verbatim and identically to all three arms.
- `rubric` — a per-task grading key that **carries the known-correct answer** (e.g. p01:
  `A = knave, B = knight, C = knight, D = knave`; p08: `final state S2, S2-count 4`).
  This is the objective correctness signal; §3.4/§3.5 consume it as a pass/fail gate on
  top of which the style rubric is scored. Do **not** discard it — it is the
  least-bias-prone signal in the whole harness.

**Category → workflow routing.** The parity arm routes on this canonical map — **not** on
a `workflows/<category>.js` filename, because several categories share one workflow:

| Category | Workflow |
|---|---|
| `deductive-reasoning` | `deep-reason` |
| `debugging` | `deep-reason` |
| `estimation` | `deep-reason` |
| `long-horizon` | `deep-reason` |
| `multi-constraint-planning` | `plan-critique` |
| `code-design` | `plan-critique` |
| `research-synthesis` | `research-synthesize` |
| `adversarial-spec` | `adversarial-verify` |

- **N = 8 today.** The shipped `eval/probe-tasks.jsonl` currently holds **8 tasks**
  (`p01`…`p08`), one per category — a smoke set, and **below** the recommended **10–20**
  band (GSD `ai-evals` reference-dataset guidance). Eight tasks give **even wider
  confidence intervals** than that band would: enough to check "does the pipeline run and
  produce a signal", not "we have proven parity". Report N with every number and never
  over-generalize (§6). Growing the set toward 10–20+ (multiple tasks per category) is the
  first thing to do before any number is quoted seriously — do not imply the 10–20 already
  exist.
- Include a difficulty spread on purpose as you grow the set. The research is explicit
  that small-model + test-time-compute matches a bigger model **only in an easy-to-medium
  band**; on the hardest tasks the gap does not close. A probe set that is all-easy will
  overstate parity; all-hard will understate the method's real (narrower) value.

### 3.2 Generate

For each task, produce three outputs:

1. `fable-raw` — one Fable pass, no scaffold.
2. `opus-raw` — one Opus pass, no scaffold.
3. `opus+fable-parity` — route the task to the workflow its category maps to (§3.1
   table), running on Opus. Each workflow takes a **different** required argument, so bind
   the prompt to the right parameter:

   | Workflow (from category) | Bind the prompt as | Notes |
   |---|---|---|
   | `deep-reason` | `task` | direct |
   | `research-synthesize` | `question` | direct |
   | `plan-critique` | `goal` | direct |
   | `adversarial-verify` | `answer` | **not** the raw prompt — see below |

   `adversarial-verify` refutes an **existing draft**; it does not answer a fresh prompt.
   So for an `adversarial-spec` task the parity arm must **first produce a draft** — an
   `opus-raw` pass over the prompt — and then feed *that draft* as `answer` for
   adversarial-verify to refute and correct. The surviving/refuted claims plus the
   corrected answer are the arm's output.

Persist **raw outputs and the full generation transcript for every arm** to disk before
judging. Judges see rendered outputs; humans auditing a disputed verdict need the raw
material. Record cost + latency per arm at generation time (§4.3) — you cannot
reconstruct token counts after the fact.

### 3.3 Anonymize + randomize (kill position/identity bias)

- **Strip identity.** Remove model names, workflow banners, "as an orchestrated
  synthesis…" tells, and any scaffold-specific formatting that leaks which arm is which.
- **Shuffle order per task.** Present the three outputs under blind labels (A/B/C) with
  a fresh random permutation for **each** task, and keep the label→arm mapping in a key
  file the judge never sees. LLM judges have a documented position bias; a fixed order
  leaks signal and inflates whichever slot you habitually put the parity arm in.
- Prefer a fixed seed for the permutation so a run is reproducible, but the seed must
  not be derivable by the judge.

### 3.4 Judge

Judging runs an **objective correctness gate first** (from the shipped per-task `rubric`,
§3.5 Layer A) and then two preference/quality modes on top — run both of the latter if
budget allows, they answer different questions:

- **(0) Objective correctness gate** — before any preference call, grade each output
  against the task's shipped `rubric` (the known-answer grading key) and record
  `correct` / `partial` / `incorrect` (or a 0–1 graded-correctness score). This is the
  primary signal and the least bias-prone one; §3.5 Layer A states exactly how the rubric
  enters the judge prompt. An arm that fails the key does not get to "win" on style.
- **(a) Pairwise preference** — show the judge two anonymized outputs, ask which is
  better for this task (allow "tie"). Do the three head-to-heads
  (`parity vs opus-raw`, `parity vs fable-raw`, `opus-raw vs fable-raw`). Pairwise is
  robust and cheap and feeds §4.1 win-rates directly.
- **(b) Absolute rubric score** — score each output per dimension on a 1/3/5 anchored
  rubric (§3.5 Layer B). Feeds §4.2 gap-closed% and the per-dimension COVERED/PARTIAL/
  MISSING report.

**Who may judge:**

- The judge **must not be Fable.** A model cannot grade its own homework — this is the
  central caveat carried over from `doublecheck` ("the same model that produced the
  output can't catch all its own errors") and the reason an independent judge is
  mandatory here. A Fable judge scoring a run that includes a `fable-raw` arm has an
  obvious self-preference conflict.
- Prefer an **independent family** (Opus- or GPT-class) and, better, a **jury** of
  diverse families rather than one judge (§5). This satisfies
  `feedback_no_solo_ai_judgment` / `external_ai_verify`. `gsd-review` and `codex`
  already wrap external CLIs to obtain such judges; compose them rather than building a
  new judge harness.
- For any verdict you intend to *report* as parity, add a **human spot-check** on at
  least a handful of tasks (§5).

### 3.5 Rubric — two layers

Judging stacks **two layers**: an objective correctness gate from the shipped per-task
`rubric` (Layer A, least bias-prone) and the 1/3/5 style rubric on top (Layer B).

**Layer A — objective correctness gate (per-task `rubric`).** Every probe line ships a
`rubric` field that *contains the known-correct answer and the grading key* (p01 →
A = knave, B = knight, C = knight, D = knave, solution unique; p08 → final state S2,
S2-count 4; p04 → the two specific defects + a concrete failing input; p02 → the unique
ordering; etc.). Use it as the primary signal:

- **How it enters the judge prompt.** For each task the judge (or jury member) is given
  three things: the task `prompt`, the anonymized candidate output, and the shipped
  `rubric` **verbatim as a grading key**. The judge is instructed: "Grade the candidate
  **against this key**, not against your own re-derivation," then emit a correctness
  verdict — `correct` / `partial` / `incorrect` (or a 0–1 graded-correctness score for
  rubrics that enumerate several required elements, e.g. p04's two defects, p06's
  adversarial cases). Because the answer is supplied, the judge is *checking, not
  solving*: the signal barely depends on the judge's own capability and is nearly immune
  to verbosity/format bias (§5), which is exactly why it is the least-bias-prone signal in
  the harness.
- The per-task rubric is **per-task, not per-arm**, so handing it to the judge leaks no
  arm identity (fable-raw can be wrong too). Keep it in the judge context for **all** arms
  identically.
- Correctness is the **gate**: an output that fails the key is not "high quality" no
  matter how well-structured. Report correctness (pass-rate / mean graded-correctness) per
  arm per category **first**, then layer style on top.

**Layer B — style/quality anchors (1/3/5).** On top of correctness, score the six
dimensions the skill is built to recover (from the gap map), plus a task-appropriate
overall-quality score. Define explicit 1/3/5 anchors per GSD `ai-evals` rubric discipline
(write the anchors **before** you see outputs):

| Dimension | 1 (weak) | 3 (adequate) | 5 (strong) |
|---|---|---|---|
| depth of multi-step reasoning | collapses the chain; drops or conflates intermediates | mostly complete chain, a couple of gaps | every dependent step derived and consumed correctly |
| catching one's own errors | ships an internal contradiction | minor slips, no major unchallenged error | contradictions surfaced and corrected before the answer |
| breadth of exploration | one approach, treated as the answer | two approaches weighed | multiple distinct (incl. non-obvious) options weighed then selected |
| planning horizon | greedy, dead-ends several steps in | workable order, minor prereq gaps | dependencies anticipated; nothing blocks downstream |
| research thoroughness | single-source claim as settled fact | several sources, thin corroboration | many threads, cross-checked, gaps/conflicts flagged, cited |
| calibration | uniform confidence; fabricated specifics | mostly hedged, some overconfidence | confidence tracks correctness; unknowns marked; no fabrication |

Layer B says *how* and *how well* an arm reasoned; Layer A decides *whether it was right*.
A parity verdict (§4.4) requires **both** — an arm that is more stylish but less often
correct against the key has **not** reached parity.

Calibrate the LLM judge against the human spot-check before trusting it: require
**≥ 0.7 correlation** with human scores on the spot-checked subset (GSD `ai-evals`
judge-calibration threshold). Below that, the judge is not trustworthy and its numbers
are reported as *indicative only*, not as the parity verdict.

---

## 4. Metrics

Report all three families. Report them **per category**; also show the aggregate but
never *only* the aggregate.

### 4.1 Per-category win-rate vs `opus-raw` (the thing to beat)

From the blind pairwise `parity vs opus-raw` comparisons, per category:

```
wins   = # tasks where opus+fable-parity was preferred over opus-raw
ties   = # tasks judged equal
losses = # tasks where opus-raw was preferred
win_rate = (wins + 0.5 * ties) / (wins + ties + losses)
```

Report the raw `wins / ties / losses` triple **alongside** `win_rate` — a 60% win-rate
built on many losses is a different story from one built on many ties, and
`feedback_benchmark_honest_disclosure` forbids hiding the losses. `win_rate ≤ 0.5` in a
category means the scaffold did not help (or hurt) there; say so plainly.

### 4.2 Gap-closed % toward `fable-raw`

Using absolute rubric scores (mean per arm, per category or per dimension), let
`S_parity`, `S_opus`, `S_fable` be the arm means:

```
gap_closed_pct = 100 * (S_parity - S_opus) / (S_fable - S_opus)
```

Interpretation and mandatory edge-case handling:

- `0%` — the scaffold added nothing over `opus-raw`.
- `100%` — the scaffold fully matched `fable-raw`.
- **`< 0%`** — the scaffold made Opus **worse** than raw. This is a real, reportable
  failure (consistent with the research warning that intrinsic self-correction can flip
  right answers to wrong). Do not clip it to zero.
- **`> 100%`** — the parity arm beat the Fable ceiling. Report literally, then
  **investigate**: usual causes are judge bias toward the scaffold's verbose/structured
  format, or tasks easy enough that all arms saturate. Treat as suspect, not triumph.
- **`S_fable ≈ S_opus` (no measurable gap, within judge noise)** — the denominator is
  ~0 and `gap_closed_pct` is **undefined and must not be computed** for that category.
  Report "no measurable Fable gap on this category (nothing to close)" instead of a
  giant or divide-by-zero number. Decide the "within noise" band from the judge's
  test-retest spread, not by eye.

Compute per **dimension** as well as per category — the whole point is to see *which*
axis (depth vs calibration vs breadth …) the scaffold actually moves.

### 4.3 Cost / latency overhead

Orchestration is not free, and the honest question is whether the quality is worth the
spend. Per task and aggregated:

```
overhead_tokens_x  = tokens(opus+fable-parity)  / tokens(opus-raw)
overhead_latency_x = walltime(opus+fable-parity) / walltime(opus-raw)
overhead_cost_x    = dollars(opus+fable-parity)  / dollars(opus-raw)
```

- Wall-clock overhead can be **lower** than token overhead because the workflows fan out
  in parallel; report both — parallelism trades money for time, and a reviewer needs to
  see which they are spending.
- Put the overhead **next to** the gap-closed number. The research is blunt that
  matching a stronger model via many samples / deep trees "is frequently not the cheaper
  trade" — a category where parity costs `8x` tokens to close `20%` of the gap is a
  *finding against the scaffold there*, and hiding the cost would misrepresent it.
- Also report the obvious alternative: for the same task, `opus+fable-parity` overhead
  vs simply *calling Fable directly* where that is an option. If direct-Fable is cheaper
  and better, say so.

### 4.4 Per-dimension parity verdict (report shape)

Reuse the `gsd-eval-review` COVERED / PARTIAL / MISSING shape, one row per (category ×
dimension), so the report reads as an audit rather than a single grade:

| Dimension | Correctness (parity vs opus-raw) | Win-rate vs opus-raw | Gap-closed % | Verdict |
|---|---|---|---|---|
| … | … | … | … | `parity_reached` / `parity_partial` / `parity_not_reached` |

The objective correctness gate (§3.5 Layer A) **binds** the verdict: `parity_reached`
requires the parity arm's correctness (pass-rate / mean graded-correctness) to be **at
least** opus-raw's. A style win with *worse* correctness against the key is
`parity_not_reached`, not parity.

Machine-readable emit uses snake_case status values (`parity_reached`,
`parity_partial`, `parity_not_reached`, `no_measurable_gap`, `regressed`), per the house
OUTPUT STYLE rule; human-facing tables use Title Case. No red/green indicators — a
"win" for the researcher arm and a "loss" for it read opposite depending on whose side
you are on, so color would mislead.

---

## 5. The judge is biased too

The judge is the measuring instrument, and it is not neutral. Known failure modes:

- **Self-preference** — a judge favors outputs from its own family. Never let Fable
  judge a run containing a Fable arm (§3.4).
- **Position bias** — favors a slot regardless of content. Mitigated by per-task
  shuffling (§3.3); verify by re-running a subset with permuted order and checking the
  verdict is stable.
- **Verbosity / format bias** — favors longer, more-structured answers. The
  `opus+fable-parity` arm is *systematically* more structured (it is a synthesis of
  several passes), so this bias points **toward** the arm under test — a direct threat
  to the headline result. Guard by normalizing formatting before judging and by human
  spot-check.
- **Correlated blind spots** — a jury of same-family models shares training data and
  therefore shares errors, so it amplifies a confident bias rather than cancelling it
  (research `key_insights`: "Diversity matters far more than raw count").

Mitigations, in order of leverage:

1. **Use a jury of diverse families**, not one judge — a panel of smaller, different
   models correlates with humans better and cheaper than a single frontier judge, with
   less intra-model bias (Verga et al. 2024, PoLL). Aggregate by vote/mean.
2. **Trust-weight the jury** rather than treating every judge equally — compose
   `multi-ai-coordination`'s `AgentTrustRegistry` (per-provider trust → weighted merge)
   so a judge with poor human-calibration counts for less.
3. **Calibrate against humans** on a spot-check subset and enforce the ≥ 0.7 correlation
   gate (§3.5) before any judge's numbers are treated as the verdict.
4. **Human spot-check every parity claim** — before reporting parity in a category, a
   human reads a handful of that category's tasks blind and confirms the direction. If
   the human disagrees with the jury, the human wins and the judge is recalibrated.
   `doublecheck`'s own limitation note ("the same model can't catch all its own errors")
   is exactly why a non-model check has to close the loop.

---

## 6. Do not over-claim (honest-disclosure guardrails)

Bind every reported number with these, per `feedback_benchmark_honest_disclosure`,
`feedback_verify_existence_before_claiming`, and the
`superpowers:verification-before-completion` Iron Law:

- **Report where parity FAILS; do not average it away.** A per-category table with a
  losing row is more honest and more useful than a single blended "78% parity". The
  failing categories are the product feedback.
- **Separate reliability from capability.** Most of these methods buy *consistency*
  (fewer variance-driven slips), not *new ability*. If the gain is "Opus already could
  do this sometimes and now does it more reliably", say that — do not sell it as Opus
  gaining a capability it lacks.
- **Respect the non-recoverables.** For tasks that need a fact the base model lacks, sit
  below the coverage floor, or are verification-hard (checking as hard as solving),
  expect **no** gain — orchestration re-ranks and prunes, it does not create capability.
  A category built on such tasks should show ~0% gap-closed, and that is the *correct*
  result, not a bug to tune away.
- **State N and uncertainty.** Report the task count, the win/tie/loss counts, and — for
  a serious claim — bootstrap confidence intervals over tasks. With the current **N = 8**
  (or even the recommended 10–20) the CIs will be wide; a wide CI that straddles "no
  effect" is not parity.
- **Design claim ≠ measured claim.** In every write-up, keep the two registers visibly
  distinct: what the skill is *designed* to do (principled, from `references/`) vs what
  a *specific run* of this harness *measured*. Never promote the former into the latter.
- **A clean sweep is a smell.** If `opus+fable-parity` wins every category and even
  matches/beats `fable-raw`, distrust it first (judge bias §5, too-easy probe set,
  identity leak) before believing it.

---

## 7. Optional: automate the harness as a workflow

The three-arm run + jury judging is itself an orchestration problem, so it can be a
small Workflow-tool script. Sketch (not shipped — build only if the manual protocol is
worth automating):

```
read eval/probe-tasks.jsonl
for each task (fan out in parallel — see superpowers:dispatching-parallel-agents):
    arm_fable  = one Fable pass
    arm_opus   = one Opus pass
    arm_parity = map task.category -> workflow (§3.1), bind prompt to that workflow's arg
                 (§3.2: task|question|goal; for adversarial-verify FIRST make an opus-raw
                 draft and pass it as `answer`), run on Opus
    persist raw outputs + transcript + {tokens, walltime, cost} per arm
anonymize + per-task shuffle -> blind A/B/C, keep label key out of judge context
dispatch a JURY of diverse, non-Fable judges in parallel (rubric given as grading key):
    objective correctness gate vs each task's shipped rubric (feeds §3.5 Layer A gate)
    pairwise preference  (feeds §4.1)
    absolute rubric score (feeds §4.2)
aggregate: per-arm correctness pass-rate (gate), per-category win-rate,
           gap-closed% (+ edge-case guards from §4.2), overhead_x,
           per-dimension COVERED/PARTIAL/MISSING verdict
emit human-readable report + machine-readable JSON (snake_case status)
flag: any category with a human/jury disagreement or gap_closed% > 100% for review
```

Hard requirements the automation must honor:

- **No Fable self-judging.** The judge roster is validated to exclude Fable before the
  run starts; a Fable arm judged by Fable aborts the run.
- **Persist everything** for human audit — raw outputs, the shuffle key, and every
  judge's ballot. A parity verdict with no saved ballots is not a verdict.
- **Attribute provenance** — tag each artifact with the tier that produced it (Fable /
  scaffold / Opus) using `multi-ai-coordination`'s `ActionTracer`, so the ledger shows
  which arm every output came from.
- **The script computes, the human ratifies.** The workflow may emit
  `parity_reached` for a category, but per §5–§6 that emit is *proposed*; a human
  spot-check ratifies it before it is reported as measured parity. The automation makes
  the measurement cheap; it does not make the claim.

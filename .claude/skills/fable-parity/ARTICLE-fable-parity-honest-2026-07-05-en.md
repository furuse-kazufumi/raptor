# Can orchestration lift Opus to a higher tier? An honest measurement

> A stronger model is about to become unavailable to me. So I built a *scaffold* — decompose,
> run diverse attempts in parallel, adversarially verify, synthesize — to try to buy back its
> per-pass quality on the Opus I'll be left with. Then I actually measured whether it worked,
> without spin.
> Short version: **it depends on the task, it doesn't reach parity uniformly, and the biggest
> win turned out to be somewhere else entirely.**

---

## 0. What this is (conclusion first)

- **What I did:** run Claude Opus not as one deep pass but as an *orchestration* (decompose →
  N diverse parallel attempts → adversarial verify → synthesize), to recover the single-pass
  quality of a stronger model (internally "Fable", a tier above Opus) — and then measure
  whether it actually gets there, using an *independent* judge.
- **The honest results:**
  1. On tasks with an objective, computable answer, **Opus is already at the ceiling** — no gap
     to the stronger model. The scaffold didn't help; on one task it even *broke itself*.
  2. On open-ended **quality** tasks (design, spec, analysis), structure finally appeared.
     **Raw single-pass Opus was never ranked first.** The stronger model won on *design/spec*
     and lost on *analysis*; the scaffold won on *analysis* and **regressed below even raw Opus**
     on a design task.
  3. The thing that clearly paid off was not quality uplift but **verification by a different
     model family** — catching a blind spot that same-family verification shares.
- **The lesson:** applying "be suspicious of results that look too good" to my own experiment,
  the tasty claim *"reached parity"* did **not** survive. What I got instead was a practical map
  of *where the scaffold helps, where a cross-family check helps, and where to add nothing.*

---

## 1. Glossary (short here; detail in the body)

| Term | One line |
|---|---|
| **Orchestration** | Coordinating several sub-agents (decompose / parallel / verify / synthesize) instead of one LLM call. |
| **Test-time compute** | Spending extra compute at inference to raise quality (here: parallel attempts + verification). |
| **Generation–verification gap** | The scaffold pays off only when *checking/selecting* an answer is cheaper than *producing* it. If verifying is as hard as solving, it degrades to base rate. |
| **Ceiling effect** | The baseline is already perfect, so there's no headroom to measure. |
| **Correlated blind spot** | Same-weight models share the same mistakes, so a confident wrong answer can win a majority vote. |
| **Perishable** | The stronger model's outputs — once access ends, they can never be re-captured. |

---

## 2. Motivation: before the stronger model disappears

The stronger model (internally "Fable", one tier above Opus) will soon be unavailable, while
daily work drops to Opus. So I need a way to *lift Opus toward that tier with a scaffold.* I built
`fable-parity`: six workflows (deep reasoning, adversarial verify, research synthesis, plan
critique, research verify, plan verify), all on top of a Workflow tool.

The thesis is simple: **a stronger model wins per pass mostly through the depth, self-correction,
and search breadth of a single inference. That edge is re-buyable by *spending orchestration* on
the Opus side — but only where the generation–verification gap is favorable.**

That was a hypothesis. The problem was that I had never *measured* whether the buy-back works.

---

## 3. Honest negative #1: objective reasoning was at the ceiling

I started with tasks that have a unique correct answer. **I did not hand-write the keys; I computed
them by brute force in Python** so an author's slip couldn't poison the benchmark. Knights-and-knaves,
constraint scheduling, multi-bug fixes, DFA traces, modular arithmetic…

Three arms (raw Opus / raw stronger-model / Opus+scaffold), graded against the key:

> **All three arms perfect. Raw Opus already solves everything single-pass.**

I raised the difficulty and tried again (60-step state machines, 4-set inclusion-exclusion, a
Wythoff game, the 50th term of a nonlinear recurrence, lattice paths…):

> **Raw Opus 9/9. 18/18 across both rounds. Zero gap to the stronger model.**

This is not the scaffold being weak — the baseline is *too perfect to measure a gap.* The scaffold's
own theory says: don't scaffold what the model already solves (it only adds cost). My experiment
landed exactly on that theory.

**And more honestly:** on the harder set, the scaffold *lost one task*. Tracing it, the synthesis
agent had shipped `{answer:"test"}` — a placeholder that satisfies the schema but is empty. In other
words, **orchestration had added a way to fail on a task raw Opus solves.** I didn't hide it; I added
a guard that falls back to the best verified attempt when the synthesis is implausibly short.

---

## 4. The pivot: what worked was cross-family verification

If everything is at the ceiling, *where* is the scaffold's value? Back to theory: its lifeline is the
generation–verification gap. But **if the verifier is also Opus, it shares the generator's weights and
its blind spots.** A confident wrong answer wins the vote. The "test" incident was exactly Opus's
self-verification waving its own error through.

So I moved *only the verification* to a different model family. I wired in OpenAI Codex (gpt-5.4,
non-Anthropic) as a refute-by-default checker (`ext_verify`) that tries to break each load-bearing
claim, and hooked it into the scaffold's verify stage.

**And it fired for real.** Running plan-verify on a FastAPI rate-limiting plan, one assumption —
"library X is Redis-native, so cross-worker sharing is automatic" — was **marked CONFIRMED by the
Opus verifier.** The **cross-family Codex refuted it with specifics**: "the current release moved to a
different implementation; that API and its retry metadata don't exist." The assumption was downgraded
to *uncertain*, and a step — *"before you start, read the code and resolve the Opus-vs-Codex
disagreement"* — was folded into the hardened plan automatically.

That is a correlated blind spot broken by a different family. An Opus-only pipeline would have shipped
the confident error. **Don't let a model grade its own homework** — that was the single change that
paid off most clearly in measurement.

---

## 5. Where structure finally appeared: the quality axis

If objective correctness is at the ceiling, then a gap between Opus and the stronger model can only
appear on the **quality** axis — depth, coverage, correctness of subtle points. There's no answer key
here, so it needs an **independent blind judge.**

On five open-ended design/spec/analysis tasks (a multi-tenant rate limiter, a total ISO-8601 duration
spec, Fibonacci vs pairing heaps, an intermittent stale-read root cause, a hot-counter concurrency
choice), I captured all three arms and had **Codex (non-Anthropic, independent of both Opus and the
stronger model) rank the anonymized answers by quality**, with a deterministic shuffle to remove
position bias.

Results (N=5, single blind judge — indicative, not statistically powered):

| Metric | Value |
|---|---|
| First-place finishes | scaffold **3/5** · stronger-model **2/5** · **raw Opus 0/5** |
| scaffold > raw Opus | **4/5** |
| stronger-model > raw Opus | **3/5** |
| scaffold > stronger-model | **3/5** |

**I then cheaply extended to 10 more tasks.** Only the stronger model's output is unre-creatable, so I
froze *that* and added raw Opus later for a 2-way blind comparison: **the stronger model beat raw Opus
7/10.** Combined, **the stronger model beats raw Opus on 10/15 open-ended quality tasks** — and the 5
tasks Opus held were clustered on *"get the subtle technical point exactly right"* (proof, numeric,
rigorous debugging).

But **the pattern matters more than the totals:**

- **Raw single-pass Opus never placed first, and lost 10/15 to the stronger model** → a single-pass
  quality gap is *real* (invisible on the objective axis). But the deficit isn't uniform: on
  proof/numeric/rigorous-debugging tasks Opus wins back.
- **The stronger model wins on breadth/design, loses on analysis** — it's not dominant. Strong where a
  single wide, well-organized pass wins; brittle where subtle technical distinctions decide it.
- **The scaffold wins where verification asymmetry is favorable, and *regresses* where it isn't** —
  it won the analysis/debugging/systems tasks but came *dead last, below raw Opus,* on the design task,
  because the synthesis/graft step breaks the coherence of one deep pass. **The scaffold isn't free and
  isn't uniformly better.**

**Honest conclusion:** "does Opus+scaffold reach the stronger model's quality?" is **task-dependent** —
it exceeds on analysis/verification-favorable work and underperforms *both* the stronger model *and* raw
Opus on at least one design task. **There is no uniform parity claim to make.** The practical answer:
*route the scaffold to analytical tasks; keep it off coherence-heavy design.*

---

## 6. The methodology is the reusable asset

- **Compute the keys.** Hand-written answers to objective tasks let an author's error poison the
  benchmark. Guarantee them by brute force / exact computation.
- **Judge with an independent family, blind.** No self-grading. Have a non-Anthropic model rank
  anonymized answers, with a deterministic shuffle to kill position bias.
- **Perishable-first.** The only unre-creatable arm is the stronger model's output. Freeze *it* cheaply
  (1 agent/task — I stored 15 quality tasks' worth); the Opus arms and the judging can come later.
- **Be suspicious of results that look too good.** "Reached parity" is tasty, but don't claim what you
  didn't measure. What survived was the modest, correct map: *it depends on the task.*

---

## 7. In one table

| Axis | Measured result | Value of the scaffold |
|---|---|---|
| Objective correctness (keyed) | Opus ≈ stronger model (**ceiling twice, 18/18**) | **None** (even a self-inflicted regression) |
| Open-ended quality (judged) | Raw Opus 0/5 firsts; loses 10/15 to the stronger model; stronger model strong on design, weak on proof/numeric | **Task-dependent** (wins on analysis, regresses on design) |
| Correlated verification blind spot | A cross-family check refuted an Opus "CONFIRMED" | **The real win** — the only thing that clearly paid off |

**With spin, I could write "orchestration made Opus reach a higher tier!" But measured honestly, I
can't say that.** What I got instead is an operational map — where the scaffold helps, where a
cross-family check helps, and where to add nothing. The value of research isn't feeling like you won;
it's disclosing the breakdown honestly. This was the session where I checked that maxim against my own
experiment.

---

*Note: all numbers are small-N, single-blind-judge indicative values, not statistically powered
benchmarks. I claim nothing beyond "this is how it came out on what I measured." The stronger model's
outputs were frozen before access ends, so this can be re-run at larger N later.*

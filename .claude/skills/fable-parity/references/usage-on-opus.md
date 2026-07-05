# Using fable-parity on Opus

This is the operator's guide. It assumes you are running Claude Code **on Opus** (not Fable/Mythos-class) and want to recover Fable-level output quality on a hard task by *spending orchestration* instead of relying on one deep pass.

> **Honesty first.** This skill is designed to close the Fable/Opus gap on principled grounds — test-time compute (parallel diverse attempts) plus adversarial verification and synthesis. It does **not** ship with a proven parity benchmark, and nothing here measures that Opus-plus-scaffold actually equals a Fable pass on your task. It buys *reliability and self-checking*, not new capability the base model lacks (see "What this cannot recover" at the end). To actually measure parity on your workload, use `eval/parity-eval.md`. Never report "reached parity" unless you ran that eval.

---

## 1. Confirm or switch to Opus

The scaffolds below assume the *session* model is Opus (that is the whole premise: a weaker-per-pass model buying back depth with orchestration).

- Check / switch interactively: run **`/model`** and select `opus` (e.g. `claude-opus-4` or whichever Opus build is current). `/model` with no argument prints the active model.
- One-shot set: **`/model opus`**.
- Verify it stuck before you spend tokens on a workflow — the model banner in `/model` output is the source of truth.

Note the sub-agents/workers a workflow spawns can each be a *different* tier. The point of fable-parity is to let cheap workers do mechanical parts while the orchestration recovers the depth. See `references/routing.md` for the per-archetype tier map.

---

## 2. The six workflows (Workflow-tool invocations)

Each workflow is a JS orchestration script under `workflows/`. You invoke it with the **Workflow tool**, passing `scriptPath` = the absolute path and `args` = the workflow's argument object. The argument shapes below are the frozen contract; defaults apply when a field is omitted.

> The Workflow tool is opt-in — see the IMPORTANT box in §3 before expecting these to run.

### 2.1 `deep-reason` — hard-reasoning uplift

Decompose → N diverse independent attempts in parallel → adversarially verify each → synthesize the best answer, grafting the strongest sub-parts. Use when a single Opus pass on a hard question/derivation/analysis would be shallow or error-prone.

```
Workflow tool
  scriptPath: D:/tools/raptor/.claude/skills/fable-parity/workflows/deep-reason.js
  args: {
    "task": "Derive the worst-case tail-latency bound for our token-bucket rate limiter under bursty arrivals, then check it against the leaky-bucket variant and state which is tighter and why.",
    "context": "Bucket size B=200, refill r=50/s, arrivals Poisson-ish with bursts up to 500. We care about p99.9, single-node, no clock skew.",
    "attempts": 3
  }
```

- `attempts` (default 3) is the fan-out width. Raise to 5 for genuinely hard problems; returns diminish — coverage rises log-linearly, and with no external verifier majority/synthesis plateaus. Don't crank it into the hundreds.

### 2.2 `adversarial-verify` — bolt-on self-checking

Extract the load-bearing claims from a draft → spawn N independent skeptics per claim prompted to **refute** (default-refuted if uncertain) → majority vote → return surviving claims, refuted claims with reasons, and a corrected answer. Use when you already have a draft/finding and want Fable-grade self-checking before shipping.

```
Workflow tool
  scriptPath: D:/tools/raptor/.claude/skills/fable-parity/workflows/adversarial-verify.js
  args: {
    "answer": "The regression was introduced in commit a1b2c3 because it changed the default timeout from 30s to 3s, which is why the nightly job now times out. The fix is to restore 30s in config/prod.yaml.",
    "claims": [
      "commit a1b2c3 changed the default timeout from 30s to 3s",
      "the nightly job times out because of that timeout change",
      "config/prod.yaml is the file that sets this default"
    ],
    "context": "Repo at D:/projects/foo. Nightly job = scripts/nightly.sh. Failure started 3 days ago.",
    "voters": 3
  }
```

- Pass `answer` alone and the workflow extracts claims itself; pass `claims` to pin exactly what gets adversarially checked (recommended for factual/citation-heavy or security findings).
- `voters` (default 3) — more decorrelated skeptics = better precision against confident-but-wrong claims. The refute-by-default posture is deliberate: it is the fix for the "model waves through its own plausible errors" failure mode.

### 2.3 `research-synthesize` — research thoroughness

Multi-modal search fan-out (each agent searches a *different* way) → dedup → deep-read the top sources → completeness-critic loop → a cited synthesis. Use for open research / survey / prior-art questions where breadth and citations matter.

```
Workflow tool
  scriptPath: D:/tools/raptor/.claude/skills/fable-parity/workflows/research-synthesize.js
  args: {
    "question": "What are the current best practices and known failure modes for using LLM-as-judge panels to score agent outputs, and how do people calibrate them against human labels?",
    "depth": "standard"
  }
```

- `depth`: `"quick"` (fast, fewer sources), `"standard"` (default), `"deep"` (wider fan-out + more deep-reads + a stricter completeness pass). Use `deep` for prior-art / novelty checks where a missed source is expensive.
- Every claim in the synthesis should carry a citation; the completeness critic flags uncovered sub-questions and conflicting sources instead of averaging them away.

### 2.4 `plan-critique` — planning depth

Generate N diverse candidate plans (different framings) → judge panel scores each on multiple lenses → synthesize the winner while grafting the best ideas of the runners-up → adversarial risk / edge-case (pre-mortem) pass. Use for a design or implementation plan where the solution space is wide and a first-draft plan would miss angles.

```
Workflow tool
  scriptPath: D:/tools/raptor/.claude/skills/fable-parity/workflows/plan-critique.js
  args: {
    "goal": "Design the migration from our single-tenant Postgres to a multi-tenant schema without downtime for existing customers.",
    "constraints": "Zero downtime, no more than 2 engineers, must be reversible at every step, existing analytics queries must keep working, 6-week window.",
    "candidates": 3
  }
```

- `candidates` (default 3) is the number of independently-framed plans. Diversity of framing matters more than raw count — the judge panel + graft step is where the value is.

### 2.5 `research-verify` — high-assurance research (research + verify, composed)

Runs `research-synthesize`, then extracts the load-bearing claims and has independent skeptics **refute** each against **primary/independent** sources → returns every claim graded **CONFIRMED / REFUTED / UNCERTAIN** plus a corrected answer. Use when a research answer will be **acted on** and cited-but-unverified is not enough.

```
Workflow tool
  scriptPath: D:/tools/raptor/.claude/skills/fable-parity/workflows/research-verify.js
  args: {
    "question": "Does the Hasani/Rus 'liquid neural network' (LTC/CfC) family actually use ReLU, or a bounded sigmoid/tanh? Verify against the primary papers and the official ncps/CfC code.",
    "depth": "standard",
    "voters": 2
  }
```

- `depth` feeds the inner `research-synthesize` (`quick`|`standard`|`deep`); `voters` (default 2) = skeptics per claim; `max_claims` (default 6) caps how many claims are verified.
- It **composes** `research-synthesize` + `adversarial-verify` in one run. The verify pass is what catches a plausible-but-wrong finding a cited-only synthesis would present as settled — prefer it over hand-chaining the two when the output drives a decision. (If `research-synthesize` is unreachable it degrades to an inline mini-sweep rather than failing.)

### 2.6 `plan-verify` — verified plan (plan + assumption-check, composed)

Runs `plan-critique`, then extracts the plan's load-bearing **assumptions** and has independent skeptics **refute** each against **primary/independent** evidence → refuted assumptions become blockers / plan changes, uncertain ones become early **validate-before-starting** steps. Use for a plan you'll actually execute where a wrong assumption is costly.

```
Workflow tool
  scriptPath: D:/tools/raptor/.claude/skills/fable-parity/workflows/plan-verify.js
  args: {
    "goal": "Add request rate limiting to our FastAPI service",
    "constraints": "Prefer a maintained library over hand-rolling; must work with FastAPI async; Redis available for shared state across workers.",
    "candidates": 3,
    "voters": 2
  }
```

- `candidates` feeds the inner `plan-critique`; `voters` (default 2) = skeptics per assumption; `max_assumptions` (default 6) caps how many are checked.
- Distinct from `plan-critique` alone: that workflow's internal pre-mortem reasons about the plan but **shares the planner's belief in its own assumptions**. `plan-verify` grounds those assumptions in external evidence — the generation–verification gap applied to *what the plan takes for granted*. (Falls back to an inline planner if `plan-critique` is unreachable.)

---

## 3. IMPORTANT: the Workflow tool is opt-in

**The Workflow tool does not fire on its own.** On Opus it runs only when the user has explicitly opted into orchestration:

- **Turn on the effort mode**: `/effort ultracode` (this is the mode that lets a skill's workflow JS actually execute), then ask for the workflow; or
- **Ask for the workflow by name** in plain language, e.g.:
  - *"use fable-parity deep-reason on this derivation"*
  - *"run fable-parity adversarial-verify on my draft finding"*
  - *"fable-parity research-synthesize this prior-art question, depth deep"*
  - *"fable-parity plan-critique this migration plan"*

Monitor running workflows with **`/workflows`**. Until the user opts in, an Opus agent must **not** silently spin up a Workflow run — fall back to the manual scaffolds in §4, which need no special mode.

Rule of thumb for *whether* to reach for a workflow at all: only when a single Opus pass would plausibly be shallow, error-prone, under-explored, or under-cited. For clear, in-competence, one-shot tasks the orchestration is pure overhead — it costs more tokens and wall-clock than just answering. Price every method per-token, not per-problem.

---

## 4. Manual fallback (no Workflow tool)

If the Workflow tool is unavailable or disallowed (no ultracode, restricted environment, or the user said no), you can approximate every workflow **by hand** using ordinary Agent dispatches — or, in the cheapest case, sequential single-context step prompts. The mechanics of parallel dispatch are documented in `superpowers:dispatching-parallel-agents` (multiple dispatches in one response run concurrently); do not re-derive them.

The shape is always the same four moves: **decompose → diverse attempts → adversarial verify → synthesize.** The independence of the attempts and of the verifier is what buys the uplift — a critic that shares the generating context inherits the same blind spot.

### 4.1 Manual `deep-reason`

**Step A — decompose (single context).** Prompt to self:
> "Restate the task. List the sub-questions that must each be answered for a correct final answer. Do not solve yet."

**Step B — N diverse attempts (parallel Agent dispatches, isolated context).** Dispatch `attempts` agents *in one message* so they run concurrently and cannot cross-contaminate. Give each a different framing so they don't collapse onto one mode:
> "You are solving this independently. TASK: <task>. CONTEXT: <context>. Approach it via <framing k> (e.g. #1 first-principles derivation, #2 by analogy to a known solved case, #3 by working back from the desired form / sanity bounds). Show all steps. State your final answer explicitly and separately at the end."

**Step C — adversarial verify each (fresh isolated context, one per attempt).**
> "Here is a candidate solution: <attempt k>. Your job is to BREAK it. Find the first wrong step, an unstated assumption, or an arithmetic/logic slip. If you cannot break it after a genuine attempt, say 'survives'. Default to skeptical."

**Step D — synthesize (single context, back in the main session).**
> "Here are N attempts and their adversarial reviews. Pick the strongest answer. Where a different attempt got a specific sub-part more correct (per its review), graft that sub-part in. Produce one final answer plus a one-line note on which parts came from where and what the reviews caught."

Cheaper single-context variant: do B as three separate prompts in sequence rather than parallel agents, then C/D inline. You lose true independence (later attempts see earlier ones in context) — weaker, but still beats one pass.

### 4.2 Manual `adversarial-verify`

**Step A — extract claims (single context).**
> "From this answer, list the load-bearing factual/logical claims as separate bullets — the ones that, if false, sink the conclusion. ANSWER: <answer>."

**Step B — refute each claim (parallel dispatches, `voters` skeptics per claim, isolated context).**
> "CLAIM: <claim>. CONTEXT: <context>. Try to REFUTE this claim with evidence or a counterexample. If you are uncertain or cannot verify it, treat it as REFUTED (default-refuted). Return: verdict {survives | refuted}, and the reason."

**Step C — majority + rewrite (single context).**
> "For each claim, take the majority verdict across its skeptics. List surviving claims, and refuted claims with the reason each fell. Then produce a corrected answer that drops or hedges every refuted claim. Mark anything you could not verify as unverified rather than asserting it."

This is the manual form of the doublecheck discipline (see §5): claim extraction → independent challenge → honest rewrite.

### 4.3 Manual `research-synthesize`

**Step A — sub-questions + search modes (single context).**
> "Break this question into sub-questions. For each, name a *different* way to search for it (keyword web search, a specific site/source, an academic/prior-art search, a code/repo search)."

**Step B — fan-out search (parallel dispatches, one per search mode).**
> "Search for <sub-question> using <mode>. Return the top sources with URLs and a 2-3 line extract of what each actually says. Do not synthesize yet."

**Step C — dedup + deep-read (single or parallel).**
> "Deduplicate the collected sources. For the top few, read them fully and pull out the load-bearing facts with citations."

**Step D — completeness critic + synthesis (single context).**
> "Draft a synthesis where every claim carries a citation. Then, as a critic, list which sub-questions are still uncovered and where sources conflict. Fill the gaps or explicitly flag them. Do not present a single-source claim as settled."

### 4.4 Manual `plan-critique`

**Step A — N candidate plans (parallel dispatches, different framings).**
> "Produce a complete plan for GOAL: <goal>. CONSTRAINTS: <constraints>. Frame it as <framing k> (e.g. #1 minimize risk / reversible-first, #2 minimize time-to-first-value, #3 minimize coordination / fewest moving parts). Give ordered steps with prerequisites."

**Step B — judge panel (single or parallel, multiple lenses).**
> "Score each plan on: correctness of ordering/dependencies, risk & reversibility, cost/effort, and constraint satisfaction. Give a 1/3/5 rating per lens with a one-line reason."

**Step C — synthesize winner + graft (single context).**
> "Pick the best-scoring plan. Graft in the strongest ideas from the runners-up where they beat the winner on a lens. Produce one merged plan."

**Step D — adversarial pre-mortem (fresh context).**
> "This plan will be executed. It is now 5 steps in and something has broken. What broke? Find unmet prerequisites, ordering problems, and dead-ends. Insert the missing steps and reorder before any execution begins."

> Manual-fallback honesty caveat: these approximate the workflows' effect; they are **not** a measured equivalent and, like the workflows, do not certify parity. When feedback can be made *external and grounded* (unit tests, a compiler/executor, a symbolic checker, a real search result), wire it into Step C/verify — external feedback is where self-correction actually pays off. Pure intrinsic self-critique with no external signal can flip right answers to wrong; don't trust it as an oracle.

---

## 5. Composing with existing skills

fable-parity is orchestration; it deliberately reuses house skills rather than reinventing them. Reach for these at the matching step:

- **`superpowers:brainstorming`** — run it *before* `deep-reason` / `plan-critique` when the framing itself is unsettled. It pushes past the first-mode solution and seeds genuinely diverse `attempts` / `candidates`, which is exactly what the fan-out step needs to not collapse onto one line of thought. (`cross-domain-ideation` / `triz-ideation` serve the same "diversify the seeds" role for TRIZ/analogy framings.)

- **`superpowers:systematic-debugging`** — the right tool when the "hard task" is a *bug*, not a derivation. Debug systematically first; if it stalls on reasoning, wrap the competing hypotheses as `deep-reason` attempts and the "which fix is right" question as `adversarial-verify` claims. Debugging's external signals (test/repro output) are the grounded feedback that makes the verify step trustworthy.

- **`doublecheck`** (`D:\tools\raptor\.claude\skills\doublecheck\SKILL.md`) — the content-correctness checker for factual/citation-heavy output. Use it as the verification engine behind `adversarial-verify` (or after `research-synthesize`) instead of hand-rolling a hallucination checker. Its own caveat — *the model that produced the output can't catch all its own errors* — is precisely why the parity **verdict** must come from an independent, non-Fable judge (Opus/GPT-class), never from self-grading.

- **`rad-research`** (`D:\tools\raptor\.claude\skills\rad-research\SKILL.md`) — inject it into the scaffold to hand the workers the domain context / prior art that a stronger model would already "know" latently. This closes the *knowledge-gap* half of the delta, which orchestration alone cannot: sampling and voting add zero information if the fact simply isn't in the model. Feed rad-research hits into the `context` arg of `deep-reason` / `plan-critique`, or run it as the first search mode in `research-synthesize`.

Typical chain: `brainstorming` (diversify framings) → `rad-research` (inject missing context) → `deep-reason` / `plan-critique` (fan-out + synthesize) → `adversarial-verify` + `doublecheck` (independent check) → an independent judge signs the parity verdict per `eval/parity-eval.md`.

---

## 6. What this cannot recover (read before claiming uplift)

Orchestration re-ranks and prunes passes the model *can* perform; it does not create capability the model lacks. It will **not** rescue:

- **Missing knowledge / facts** — every sample is wrong the same way. Fix with retrieval/tools (`rad-research`, web search), not more attempts.
- **Anything below the coverage floor** — if the correct answer is never in the sample distribution, no selector, judge, or vote surfaces it.
- **Verification-hard tasks with no asymmetry** — when checking is as hard as solving (open-ended judgment, novel claims with no ground truth), the verifier is as wrong as the generator and the scheme degenerates to base rate.
- **Systematic, correlated errors** — shared-weight samples share blind spots, so a confident wrong answer can *win* the majority vote. This is why diversity (different framings, genuinely adversarial roles, ideally different model families for judges) matters far more than raw count.

If a task hits one of these, say so plainly and route to the real fix (tools/retrieval, a stronger model, or a human) rather than spending more orchestration. And never state "Fable parity achieved" without running `eval/parity-eval.md` — this file gives you the recipe, not the receipt.

---

## 7. GPU / ローカルモデル環境への展開（将来）

The same lever generalizes **downward**, not only up to Opus. When you move to a local GPU box and run a self-hosted model (a small Qwen/Llama, an `llcore`/`llive` checkpoint, etc.), that model is *weaker per pass than Opus* — so these scaffolds help **more**, and local compute makes the orchestration **cheaper** (no per-token API bill, only wall-clock and electricity).

- **Point the workers at the local model.** fable-parity is model-agnostic: it only spends `agent()` calls. On a local host, route the workflow's worker agents to the local endpoint (the session model, or an OpenAI-compatible base URL) so fan-out + verify run fully on-prem. The recipe is unchanged; only the backend moves.
- **Cheap compute shifts the trade.** The §6 *dollar/token* caveat softens on your own GPU — best-of-N and larger `attempts` / `candidates` / `depth` become affordable, so raise them. The *latency* caveat still stands (parallel dispatch + serial verify add wall-clock).
- **Keep the verifier independent.** The whole skill rests on the generation–verification gap. A local judge that shares weights with the local generator has correlated blind spots — prefer a *different* local model, a cloud judge, or a human for the parity verdict (`eval/parity-eval.md`). Never let a model grade its own homework.
- **On-prem by design.** Nothing leaves the box; this fits the FullSense "local is the AI's home" stance. Measure parity locally with `eval/parity-eval.md` before asserting a small local model reaches Opus/Fable on your workload.

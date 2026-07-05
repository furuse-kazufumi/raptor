export const meta = {
  name: "deep-reason",
  description:
    "General hard-reasoning uplift for Opus: decompose a hard task, run N diverse independent solver attempts in parallel (each a different framing), adversarially verify each, then synthesize the final answer by grafting the strongest verified sub-parts. Buys back Fable-tier per-pass depth by spending orchestration; it does NOT create capability the base model lacks (missing facts, below-coverage answers, verification-hard tasks stay unrecoverable).",
  phases: [
    { title: "Decompose", detail: "One agent restates the task and produces a schema-structured skeleton: sub-questions, approach steps, success criteria, likely pitfalls." },
    { title: "Attempt", detail: "Run N independent solver agents in parallel, each forced onto a DIFFERENT framing (first-principles / work-backwards / analogy-to-known-result / adversarial-edge-first, cycled by index) so they do not collapse onto one line of thought." },
    { title: "Verify", detail: "For each attempt, an adversarial checker in a clean context hunts fatal flaws and unjustified steps and returns a verdict (sound / salvageable / broken)." },
    { title: "Synthesize", detail: "One agent reads every attempt, its verification, and the decomposition, then grafts the strongest verified sub-parts into a single answer, resolves disagreements, and attaches a confidence note plus surviving dissent." }
  ]
};

// ---- Inputs ---------------------------------------------------------------
// Accept args as an object, a JSON string, or a bare string (taken as the task).
// The Workflow tool is meant to pass an object, but some callers stringify it.
const A = (function () {
  if (args && typeof args === "object") return args;
  if (typeof args === "string") {
    const s = args.trim();
    if (s.startsWith("{")) { try { return JSON.parse(s); } catch (_) { /* fall through */ } }
    return { task: s };
  }
  return {};
})();
const task = (typeof A.task === "string" && A.task.trim())
  ? A.task.trim()
  : "(no task provided)";
const context = (typeof A.context === "string" && A.context.trim())
  ? A.context.trim()
  : "";
const requestedAttempts = Number.isFinite(Number(A.attempts))
  ? Number(A.attempts)
  : 3;
// Clamp to a sane, budget-friendly range (Math.random is forbidden; Math.max/min are fine).
const attemptsN = Math.max(2, Math.min(6, Math.trunc(requestedAttempts) || 3));

// Heterogeneous verify: after the Opus adversarial check, cross-check each attempt's
// conclusion with an INDEPENDENT non-Opus family (OpenAI Codex via bin/ext_verify.py).
// Opus-only verification shares the generator's blind spots (2026-07-05 baseline shipped
// a degenerate synthesis). Default ON but fully degrading: if the external relay yields
// nothing usable, ranking/synthesis proceed exactly as before. Pass external_verify:false
// for byte-identical prior behavior (e.g. controlled evals).
const externalVerify = A.external_verify !== false && String(A.external_verify).toLowerCase() !== "off";
const EXT_VERIFY_PATH = "D:/tools/raptor/.claude/skills/fable-parity/bin/ext_verify.py";

// Diverse framings. Varied by attempt index so parallel solvers do not converge
// on one mode. Correlated-error mitigation: diversity matters more than raw N.
const FRAMINGS = [
  {
    key: "first-principles",
    guidance:
      "Solve strictly from first principles. Do NOT pattern-match to a remembered template. Build up from definitions and the given constraints, justifying every inferential step. State each intermediate result explicitly before using it."
  },
  {
    key: "work-backwards-from-answer",
    guidance:
      "Work backwards. Hypothesize the SHAPE of a correct final answer, then derive what must be true for it to hold, checking each necessary condition against the task. If a required condition cannot be met, revise the hypothesized answer and repeat."
  },
  {
    key: "analogy-to-known-result",
    guidance:
      "Reason by analogy to a known result, standard technique, or canonical solved problem that this task resembles. Name the analog explicitly, map each part of the task onto it, then flag every place the analogy BREAKS and handle those specially rather than assuming the analogy carries through."
  },
  {
    key: "adversarial-edge-first",
    guidance:
      "Attack the hardest part first. Enumerate the edge cases, boundary conditions, and failure modes BEFORE proposing a main-line solution, then construct an answer that already survives them. Prefer an answer that is provably robust to the nasty cases over an elegant one that only handles the typical case."
  },
  {
    key: "constraint-propagation",
    guidance:
      "Treat this as constraint satisfaction. List every constraint the answer must satisfy, propagate them to prune the solution space, and only then commit. Make the binding constraints explicit and show the answer respects each one."
  },
  {
    key: "decompose-and-recompose",
    guidance:
      "Split the task into the smallest independently-solvable pieces, solve each in isolation to stay within a single reliable pass, then recompose — explicitly checking that the pieces' interfaces line up and nothing was dropped at the seams."
  }
];

// ---- Schemas --------------------------------------------------------------
const DECOMP_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    restated_task: { type: "string", description: "The task in your own words, disambiguated." },
    sub_questions: { type: "array", items: { type: "string" }, description: "The decisive sub-questions that must be answered." },
    approach_skeleton: { type: "array", items: { type: "string" }, description: "Ordered steps of a viable approach (a skeleton, not a full solution)." },
    success_criteria: { type: "array", items: { type: "string" }, description: "What a correct final answer must satisfy." },
    likely_pitfalls: { type: "array", items: { type: "string" }, description: "Where a shallow single pass would slip." }
  },
  required: ["restated_task", "sub_questions", "approach_skeleton", "success_criteria"]
};

const ATTEMPT_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    framing: { type: "string", description: "The framing you were assigned." },
    reasoning_steps: { type: "array", items: { type: "string" }, description: "Each dependent step, with its intermediate result written out explicitly." },
    key_assumptions: { type: "array", items: { type: "string" }, description: "Assumptions the answer rests on." },
    answer: { type: "string", description: "The full candidate answer this framing produces." },
    self_confidence: { type: "string", enum: ["low", "medium", "high"], description: "Honest confidence, hedged where genuinely uncertain." }
  },
  required: ["framing", "reasoning_steps", "answer", "self_confidence"]
};

const VERIFY_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    fatal_flaws: {
      type: "array",
      description: "Errors that, if real, break the answer. Empty only if you genuinely found none after trying to break it.",
      items: {
        type: "object",
        additionalProperties: false,
        properties: {
          step: { type: "string", description: "Which step/claim is broken." },
          why: { type: "string", description: "Why it is wrong or unjustified." }
        },
        required: ["why"]
      }
    },
    unjustified_steps: { type: "array", items: { type: "string" }, description: "Steps that are asserted without adequate justification (even if possibly true)." },
    salvageable_parts: { type: "array", items: { type: "string" }, description: "Sub-parts of this attempt that are sound and worth grafting into the final answer." },
    verdict: { type: "string", enum: ["sound", "salvageable", "broken"], description: "Overall verdict. Default toward 'broken' or 'salvageable' if you are uncertain — do not wave through plausible-but-unchecked reasoning." }
  },
  required: ["fatal_flaws", "verdict"]
};

const SYNTH_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    answer: { type: "string", description: "The final synthesized answer, grafting the strongest verified sub-parts." },
    confidence: { type: "string", enum: ["low", "medium", "high"], description: "Overall confidence in the final answer." },
    confidence_note: { type: "string", description: "One short paragraph: why this confidence, and what could still be wrong." },
    grafted_from: { type: "array", items: { type: "string" }, description: "Which attempt framings each key part of the final answer came from." },
    dissent: { type: "array", items: { type: "string" }, description: "Surviving disagreements or unresolved alternatives worth flagging — do NOT average these away." }
  },
  required: ["answer", "confidence", "confidence_note"]
};

// ---- Prompt builders ------------------------------------------------------
const contextBlock = context ? `\n\nSHARED CONTEXT:\n${context}\n` : "\n";

function decomposePrompt() {
  return [
    "You are decomposing a hard reasoning task before any attempt is made to solve it.",
    "Do NOT solve it. Produce a structured skeleton that later independent solvers will each attack from a different angle.",
    "Be specific: the sub-questions should be the ones that actually decide the answer, and the pitfalls should name where a single shallow pass would go wrong.",
    contextBlock,
    "TASK:",
    task
  ].join("\n");
}

function attemptPrompt(item, decomp) {
  const decompBlock = decomp
    ? `\n\nDECOMPOSITION (shared skeleton — use it, but reason INDEPENDENTLY):\n${JSON.stringify(decomp, null, 2)}\n`
    : "\n";
  return [
    "You are ONE independent solver among several working the SAME task in parallel. You cannot see the others.",
    "Your job is to produce the best complete answer you can UNDER YOUR ASSIGNED FRAMING. Commit to the framing even if another angle feels easier — diversity across solvers is the point.",
    "",
    `ASSIGNED FRAMING: ${item.framing}`,
    item.guidance,
    "",
    "Discipline: write out every dependent step and its intermediate result explicitly (do not carry it only in your head). Hedge genuinely uncertain claims rather than stating guesses as facts.",
    decompBlock,
    contextBlock,
    "TASK:",
    task
  ].join("\n");
}

function verifyPrompt(attempt) {
  return [
    "You are an ADVERSARIAL checker in a clean context. You did not write the answer below and you owe it no charity.",
    "Your ONLY job is to break it: find fatal flaws, arithmetic/logic slips, and steps asserted without justification. Actively try to construct a counterexample.",
    "Rules: if you are uncertain whether a step holds, treat it as unjustified rather than assuming it is fine. A confident tone is not evidence. Do not invent flaws that are not there, but do not wave through plausible-but-unchecked reasoning either.",
    "Also note which sub-parts ARE sound and worth salvaging.",
    contextBlock,
    "ORIGINAL TASK:",
    task,
    "",
    "CANDIDATE ATTEMPT TO ATTACK:",
    JSON.stringify(attempt, null, 2)
  ].join("\n");
}

const EXT_RELAY_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    results: {
      type: "array",
      description: "One entry per attempt, in the same order given.",
      items: {
        type: "object",
        additionalProperties: false,
        properties: {
          framing: { type: "string" },
          claim: { type: "string", description: "The distilled one/two-sentence conclusion you verified." },
          verdict: { type: "string", enum: ["survives", "refuted", "unverified"] },
          reason: { type: "string" },
          ok: { type: "boolean" }
        },
        required: ["framing", "verdict", "ok"]
      }
    }
  },
  required: ["results"]
};

// One relay dispatch: distill each attempt's conclusion to a SHORT claim (safe for a
// shell arg) and cross-check it with the external non-Opus verifier. Short distilled
// claims avoid the quoting/length fragility of passing a full multi-step answer to Bash.
function extRelayPrompt(attemptsForExt) {
  const block = attemptsForExt
    .map((a) => `--- framing: ${a.framing} ---\n${a.answer}`)
    .join("\n\n");
  return [
    "You relay to an EXTERNAL, non-Opus verifier (a different model family) to cross-check each attempt's CONCLUSION independently.",
    "For EACH attempt below:",
    "1. Distill its final conclusion into ONE short, self-contained claim (<= 2 sentences, no code fences). Include the specific final result (the number/assignment/answer), since that is what must be checked.",
    "2. Run this EXACT command with the Bash tool, substituting your distilled claim for <CLAIM> (escape embedded quotes so the shell command stays valid):",
    "",
    "   py -3.11 \"" + EXT_VERIFY_PATH + "\" --model codex --claim \"<CLAIM>\" --timeout 180",
    "",
    "3. It prints ONE JSON line like {\"model\":\"codex\",\"verdict\":\"survives\"|\"refuted\",\"reason\":\"...\",\"ok\":true}. Use EXACTLY what it prints; never invent a verdict. If a run errors or prints ok:false, record the verdict as printed (default 'refuted') with ok:false.",
    "",
    "ORIGINAL TASK (for context on what the conclusion should answer):",
    task,
    "",
    "ATTEMPTS (distill each one's conclusion):",
    block,
    "",
    "Return { results: [ {framing, claim, verdict, reason, ok}, ... ] } with one entry per attempt, preserving order."
  ].join("\n");
}

function synthesizePrompt(decomp, verifiedAttempts) {
  return [
    "You are synthesizing a single final answer from several independent attempts and their adversarial verifications.",
    "Method:",
    "1. Weight attempts by their verification verdict: prefer 'sound', then graft 'salvageable_parts' from partially-broken ones, and DISCARD reasoning marked with fatal flaws. Also treat an attempt whose `external_verdict` is 'refuted' (an INDEPENDENT non-Opus family broke its conclusion) as suspect: do not lead with it, and drop its conclusion unless another attempt independently confirms it.",
    "2. Where attempts AGREE via independent framings, that convergence is real signal — trust it more.",
    "3. Where they DISAGREE, resolve it on the merits using the verifications; if it cannot be resolved, keep it as explicit dissent rather than papering over it.",
    "4. Do not introduce new claims that no attempt made and no verification supports. If a required piece is missing or unknowable, say so plainly instead of fabricating specifics.",
    "5. Calibrate confidence to what actually survived verification, not to how clean the prose reads.",
    context ? `\nSHARED CONTEXT:\n${context}\n` : "\n",
    "ORIGINAL TASK:",
    task,
    "",
    "DECOMPOSITION:",
    JSON.stringify(decomp, null, 2),
    "",
    "ATTEMPTS WITH THEIR VERIFICATIONS:",
    JSON.stringify(verifiedAttempts, null, 2)
  ].join("\n");
}

// ---- Phase 1: Decompose ---------------------------------------------------
phase("Decompose");
log(`Decomposing the task before spending ${attemptsN} parallel attempts.`);
let decomposition = null;
try {
  decomposition = await agent(decomposePrompt(), {
    schema: DECOMP_SCHEMA,
    phase: "Decompose",
    label: "decompose"
  });
} catch (e) {
  // A schema-retry-cap failure THROWS rather than returning null; catch it so a
  // decomposition failure degrades gracefully instead of killing the run.
  log("Decomposition agent errored (" + (e && e.message) + "); proceeding without it.");
}
if (!decomposition) {
  log("No decomposition; solvers will proceed without a shared skeleton.");
}

// ---- Build the attempt items (framing varied by index) --------------------
const items = [];
for (let i = 0; i < attemptsN; i++) {
  const f = FRAMINGS[i % FRAMINGS.length];
  items.push({ index: i, framing: f.key, guidance: f.guidance });
}

// ---- Phases 2 & 3: Attempt (parallel) then Verify (adversarial per attempt)
// Each item flows independently: solve -> immediately hand to an adversarial
// checker. No barrier between the stages, so verification of a fast attempt
// starts while slower attempts are still solving.
log(`Launching ${items.length} independent solver attempts with distinct framings.`);
const verifiedRaw = await pipeline(
  items,
  (item) =>
    agent(attemptPrompt(item, decomposition), {
      schema: ATTEMPT_SCHEMA,
      phase: "Attempt",
      label: "attempt:" + item.framing
    }),
  (attempt, item) => {
    if (!attempt) return null; // solver died -> drop this branch
    return agent(verifyPrompt(attempt), {
      schema: VERIFY_SCHEMA,
      phase: "Verify",
      label: "verify:" + item.framing
    }).then((verification) => ({
      framing: item.framing,
      attempt,
      verification: verification || {
        fatal_flaws: [],
        verdict: "broken",
        unjustified_steps: ["verification agent failed to return; treated as unverified"]
      }
    }));
  }
);

const verified = verifiedRaw.filter(Boolean);
log(`Verified ${verified.length}/${items.length} attempts survived to synthesis.`);

// ---- Heterogeneous cross-check: independent non-Opus verdict per attempt ----
// Additive and fully degrading: annotates verified[i].external; never removes an
// attempt. Any failure leaves verified untouched (prior behavior preserved).
if (externalVerify && verified.length > 0) {
  try {
    const attemptsForExt = verified.map((v) => ({ framing: v.framing, answer: v.attempt.answer || "" }));
    const relay = await agent(extRelayPrompt(attemptsForExt), {
      schema: EXT_RELAY_SCHEMA,
      phase: "Verify",
      label: "ext-verify:codex"
    });
    const results = (relay && Array.isArray(relay.results)) ? relay.results : [];
    let usableCount = 0;
    for (const v of verified) {
      const r = results.find((x) => x && x.framing === v.framing);
      if (r && r.ok) usableCount += 1;
      v.external = r
        ? { verdict: r.verdict, reason: r.reason || "", claim: r.claim || "", usable: !!r.ok, model: "codex" }
        : { verdict: "unverified", reason: "no external result for this attempt", usable: false, model: "codex" };
    }
    log(`External non-Opus cross-check: ${usableCount}/${verified.length} attempts got a usable codex verdict.`);
  } catch (e) {
    log("External verify relay errored (" + (e && e.message) + "); proceeding with Opus verification only.");
    for (const v of verified) if (!v.external) v.external = { verdict: "unverified", reason: "external relay failed", usable: false, model: "codex" };
  }
}

// Order best-first so synthesis and the summary lead with the strongest material.
// Primary key = Opus adversarial verdict; secondary = external refutation penalty, so
// an attempt the independent family refuted does not lead synthesis over a clean peer.
const verdictRank = { sound: 0, salvageable: 1, broken: 2 };
const extPenalty = (v) => (v.external && v.external.usable && v.external.verdict === "refuted" ? 1 : 0);
verified.sort((a, b) => {
  const primary = (verdictRank[a.verification.verdict] ?? 3) - (verdictRank[b.verification.verdict] ?? 3);
  if (primary !== 0) return primary;
  return extPenalty(a) - extPenalty(b);
});

// ---- Phase 4: Synthesize --------------------------------------------------
// Pass a COMPACTED view of the attempts (drop the verbose per-step traces) so the
// synthesis input/output stays small enough to reliably satisfy the schema — the
// full reasoning_steps arrays can bloat the call to a schema-retry-cap failure.
const verifiedForSynth = verified.map((v) => ({
  framing: v.framing,
  answer: v.attempt.answer,
  key_assumptions: v.attempt.key_assumptions || [],
  self_confidence: v.attempt.self_confidence || "unknown",
  verification: {
    verdict: v.verification.verdict,
    fatal_flaws: v.verification.fatal_flaws || [],
    unjustified_steps: v.verification.unjustified_steps || [],
    salvageable_parts: v.verification.salvageable_parts || []
  },
  // Independent non-Opus verdict on this attempt's conclusion (may be absent).
  external_verdict: v.external && v.external.usable
    ? { verdict: v.external.verdict, reason: v.external.reason }
    : null
}));

phase("Synthesize");
let synthesis = null;
if (verified.length > 0) {
  try {
    synthesis = await agent(synthesizePrompt(decomposition, verifiedForSynth), {
      schema: SYNTH_SCHEMA,
      phase: "Synthesize",
      label: "synthesize"
    });
  } catch (e) {
    // Do not let a synthesis schema-retry-cap failure kill the run; fall through
    // to the best-verified-attempt fallback below.
    log("Synthesis agent errored (" + (e && e.message) + "); using best-verified attempt fallback.");
  }
}

// ---- Assemble return value (robust to agent failures) ---------------------
const attempts_summary = verified.map((v) => ({
  framing: v.framing,
  verdict: v.verification.verdict,
  fatal_flaw_count: Array.isArray(v.verification.fatal_flaws)
    ? v.verification.fatal_flaws.length
    : 0,
  self_confidence: v.attempt.self_confidence || "unknown",
  external_verdict: v.external && v.external.usable ? v.external.verdict : (v.external ? "unverified" : null),
  answer_excerpt: (v.attempt.answer || "").slice(0, 400)
}));

// Heterogeneous-verify summary: where the independent non-Opus family refuted an
// attempt the Opus checker had passed (sound/salvageable) — the correlated-blind-spot
// catches this cross-check exists to surface.
const external_summary = externalVerify
  ? {
      enabled: true,
      usable: verified.filter((v) => v.external && v.external.usable).length,
      total: verified.length,
      external_only_catches: verified
        .filter((v) => v.external && v.external.usable && v.external.verdict === "refuted" && v.verification.verdict !== "broken")
        .map((v) => ({ framing: v.framing, opus_verdict: v.verification.verdict, external_reason: v.external.reason }))
    }
  : { enabled: false };

// Guard against a degenerate-but-schema-valid synthesis. The SYNTH_SCHEMA only
// requires `answer` to be a string, so a model that emits a placeholder (observed
// in the 2026-07-05 baseline: {answer:"test", confidence:"high", confidence_note:"test"}
// on a debugging task) passes schema validation and would otherwise ship as the
// final answer. If real attempts existed but the synthesized answer is implausibly
// short, treat synthesis as failed and fall through to the best-verified attempt.
const maxAttemptLen = verified.reduce(
  (m, v) => Math.max(m, ((v.attempt && v.attempt.answer) || "").trim().length),
  0
);
const synthAnswer = (synthesis && typeof synthesis.answer === "string") ? synthesis.answer.trim() : "";
const synthesisDegenerate = synthesis && synthAnswer.length < 40 && maxAttemptLen >= 120;
if (synthesisDegenerate) {
  log("Synthesis produced a degenerate answer (" + JSON.stringify(synthAnswer).slice(0, 40) +
      ", " + synthAnswer.length + " chars vs best attempt " + maxAttemptLen +
      "); discarding it and using best-verified attempt fallback.");
}

if (synthesis && !synthesisDegenerate) {
  return {
    answer: synthesis.answer,
    confidence: synthesis.confidence,
    confidence_note: synthesis.confidence_note,
    dissent: Array.isArray(synthesis.dissent) ? synthesis.dissent : [],
    grafted_from: Array.isArray(synthesis.grafted_from) ? synthesis.grafted_from : [],
    attempts_summary,
    external_summary
  };
}

// Fallback: synthesis unavailable — surface the best-ranked surviving attempt
// honestly rather than fabricating a synthesized answer.
const best = verified[0];
return {
  answer: best ? best.attempt.answer : "No attempt survived verification; unable to produce an answer.",
  confidence: "low",
  confidence_note: best
    ? "Synthesis step did not complete; returning the single best-verified attempt (" + best.framing + ", verdict " + best.verification.verdict + ") unmerged. Treat as provisional."
    : "Both the solver and synthesis stages failed to yield a usable result. No parity claim is made; re-run or escalate.",
  dissent: verified.slice(1).map((v) => v.framing + " (" + v.verification.verdict + ") offered a different answer that was not merged."),
  grafted_from: best ? [best.framing] : [],
  attempts_summary,
  external_summary
};

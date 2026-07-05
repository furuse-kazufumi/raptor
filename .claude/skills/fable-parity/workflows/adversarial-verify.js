export const meta = {
  name: "adversarial-verify",
  description:
    "Bolt-on Fable-grade self-checking for an Opus-produced answer. Extract the load-bearing factual/logical claims, then for EACH claim spawn N independent skeptics in parallel that are prompted to REFUTE it and to default to refuted when genuinely uncertain; a claim survives only if a MAJORITY of skeptics fail to break it. Finally rewrite the answer removing/flagging refuted claims and noting residual uncertainty. This buys precision against confident-but-wrong claims; it is NOT a measured parity benchmark and, because skeptics share the base model's weights, correlated blind spots can survive — see eval/parity-eval.md to actually measure parity.",
  phases: [
    { title: "Extract", detail: "If claims were not supplied, one agent extracts the atomic, self-contained load-bearing claims (factual and logical) the answer's correctness depends on. Skipped when claims are passed in directly." },
    { title: "Refute", detail: "For each claim independently, N diverse skeptics run in parallel, each on a different refutation angle (counterexample / fabricated-specific / overreach / logical-consistency / hidden-assumption). Each is told to actively break the claim and default to refuted when uncertain. A claim survives only if a strict majority fail to refute it." },
    { title: "Revise", detail: "One agent rewrites the answer: drop or clearly flag every refuted claim with its reason, keep the survivors, add a residual-uncertainty note for weak survivors, and introduce no new claims." }
  ]
};

// ---- Inputs ---------------------------------------------------------------
// Accept args as an object, a JSON string, or a bare string (taken as the answer).
// The Workflow tool is meant to pass an object, but some callers stringify it.
const A = (function () {
  if (args && typeof args === "object") return args;
  if (typeof args === "string") {
    const s = args.trim();
    if (s.startsWith("{")) { try { return JSON.parse(s); } catch (_) { /* fall through */ } }
    return { answer: s };
  }
  return {};
})();
const rawAnswer = (typeof A.answer === "string") ? A.answer.trim() : "";
const context = (typeof A.context === "string" && A.context.trim())
  ? A.context.trim()
  : "";

// Voters default 3; clamp to a sane range. Ties break toward refuted (fail-closed).
const requestedVoters = Number.isFinite(Number(A.voters))
  ? Number(A.voters)
  : 3;
const votersN = Math.max(2, Math.min(7, Math.trunc(requestedVoters) || 3));

// Pre-supplied claims (coerced to non-empty strings) let us skip extraction.
function coerceClaim(c) {
  if (typeof c === "string") return c.trim();
  if (c && typeof c === "object" && typeof c.text === "string") return c.text.trim();
  if (c && typeof c === "object" && typeof c.claim === "string") return c.claim.trim();
  return "";
}
const suppliedClaims = Array.isArray(A.claims)
  ? A.claims.map(coerceClaim).filter(Boolean)
  : [];

// Diverse skeptic angles, cycled by voter index so the N skeptics on one claim
// attack from DIFFERENT directions. Correlated-error mitigation: diversity of
// refutation strategy matters more than raw voter count.
const SKEPTIC_ANGLES = [
  {
    key: "counterexample-hunt",
    guidance:
      "Try to construct a concrete counterexample or a case in which the claim is FALSE. If any plausible input/scenario makes it fail, it is refuted. A claim that is only 'usually' true is refuted if stated as universal."
  },
  {
    key: "fabricated-specific",
    guidance:
      "Assume the claim smuggles in a fabricated specific (a nonexistent API/function name, a made-up citation, an invented number, a wrong file path, an over-precise figure). You have NO web/tools: if the claim asserts a specific external fact you cannot confirm from the provided context or firm common knowledge, treat it as unverified and refute it (fabrication risk)."
  },
  {
    key: "overreach-scope",
    guidance:
      "Attack the scope. Is the claim overgeneralized beyond what actually holds — an absolute ('always', 'never', 'guarantees', 'proven') where only a qualified statement is warranted? If the strong form is unsupported, refute it even if a weaker form would be fine."
  },
  {
    key: "logical-consistency",
    guidance:
      "Check the claim's internal logic and its consistency with the rest of the answer and the context. Does it follow from what precedes it, or is it a non-sequitur / circular / contradicted elsewhere? An unjustified inferential leap is a refutation."
  },
  {
    key: "hidden-assumption",
    guidance:
      "Surface the unstated assumptions the claim depends on. If it silently requires a premise that is not given, not established, or likely false, the claim is refuted until that premise is justified."
  },
  {
    key: "definition-ambiguity",
    guidance:
      "Attack ambiguity. If a key term is used in a slippery or shifting sense so that the claim is only 'true' under a reading the answer does not actually commit to, treat the load-bearing reading as unsupported and refute it."
  }
];

// ---- Schemas --------------------------------------------------------------
const EXTRACT_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    claims: {
      type: "array",
      description: "The load-bearing claims (factual and logical) the answer's correctness rests on. Each must be atomic and self-contained enough that a skeptic can judge it without re-reading the whole answer. Exclude hedges, restatements, and rhetorical filler.",
      items: { type: "string" }
    }
  },
  required: ["claims"]
};

const VOTE_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    refuted: {
      type: "boolean",
      description: "true if you broke the claim OR you are genuinely uncertain it holds (default to true under uncertainty). false ONLY if the claim is clearly correct/well-founded on its face or from the provided context."
    },
    reason: {
      type: "string",
      description: "The specific flaw, counterexample, missing justification, or unverifiable specific — or, if not refuted, why it clearly holds."
    },
    confidence: {
      type: "string",
      enum: ["low", "medium", "high"],
      description: "Your confidence in THIS verdict."
    }
  },
  required: ["refuted", "reason", "confidence"]
};

const REVISE_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    revised_answer: {
      type: "string",
      description: "The rewritten answer: refuted claims removed or explicitly flagged with a brief reason, survivors kept, no new claims introduced. If there was no original answer, a careful statement assembled only from surviving claims."
    },
    residual_uncertainty: {
      type: "array",
      items: { type: "string" },
      description: "Survivors that passed only weakly, or gaps that remain — surfaced honestly, not averaged away."
    },
    removed_claims: {
      type: "array",
      items: { type: "string" },
      description: "Claims dropped or flagged as refuted in the rewrite."
    }
  },
  required: ["revised_answer"]
};

// ---- Prompt builders ------------------------------------------------------
const contextBlock = context ? `\n\nSHARED CONTEXT:\n${context}\n` : "\n";

function extractPrompt(answer) {
  return [
    "You are extracting the load-bearing claims from an answer so each can be independently stress-tested by skeptics.",
    "Include both FACTUAL claims (specific facts, names, numbers, citations, API/file references) and LOGICAL claims (inferential steps the conclusion rests on).",
    "Rules: make each claim ATOMIC (one assertion) and SELF-CONTAINED (understandable without the surrounding text). Do NOT include hedges, restatements, or rhetorical filler. If the answer's conclusion depends on it, extract it; if removing it would not change correctness, skip it.",
    contextBlock,
    "ANSWER TO DECOMPOSE INTO CLAIMS:",
    answer
  ].join("\n");
}

function refutePrompt(claim, angle, voterIndex) {
  return [
    "You are an INDEPENDENT skeptic in a clean context. You did not write the claim below and you owe it no charity.",
    "Your ONLY job is to REFUTE the claim: prove it false, unsupported, overreaching, or unverifiable. Actively try to break it before considering that it might hold.",
    "",
    `REFUTATION ANGLE (skeptic #${voterIndex + 1}, focus: ${angle.key}):`,
    angle.guidance,
    "",
    "Decision rule: set refuted=true if you break it OR if you are genuinely uncertain whether it holds — a confident tone in the claim is not evidence. Set refuted=false ONLY when the claim is clearly correct and well-founded on its face or from the provided context. Do not invent flaws that are not there, but do not wave through plausible-but-unchecked assertions either.",
    contextBlock,
    "CLAIM TO REFUTE:",
    claim
  ].join("\n");
}

function revisePrompt(answer, survivingClaims, refutedClaims) {
  return [
    "You are producing a corrected answer after adversarial verification of its claims.",
    "Method:",
    "1. REMOVE or clearly FLAG every refuted claim; where a refuted claim was load-bearing, adjust the surrounding conclusion instead of leaving it dangling.",
    "2. KEEP the surviving claims. Do NOT introduce any new claim that was not in the original answer and did not survive verification.",
    "3. For survivors that passed only weakly, add an honest residual-uncertainty note rather than restating them as settled fact.",
    "4. If there was no original answer, assemble a careful statement using ONLY the surviving claims, and say plainly where refuted claims left gaps.",
    "5. Do not fabricate specifics to fill a hole left by a refuted claim — say the gap exists.",
    context ? `\nSHARED CONTEXT:\n${context}\n` : "\n",
    "ORIGINAL ANSWER (may be empty):",
    answer || "(no original answer was provided; only claims were verified)",
    "",
    "SURVIVING CLAIMS (majority of skeptics failed to refute):",
    JSON.stringify(survivingClaims, null, 2),
    "",
    "REFUTED CLAIMS WITH SKEPTIC REASONS (majority refuted, or unverifiable):",
    JSON.stringify(refutedClaims, null, 2)
  ].join("\n");
}

// ---- Resolve the claim list (from args, else extract) ---------------------
let claims = suppliedClaims;
if (claims.length === 0 && rawAnswer) {
  phase("Extract");
  log("No claims supplied; extracting load-bearing claims from the answer.");
  const extracted = await agent(extractPrompt(rawAnswer), {
    schema: EXTRACT_SCHEMA,
    phase: "Extract",
    label: "extract"
  });
  if (extracted && Array.isArray(extracted.claims)) {
    claims = extracted.claims.map(coerceClaim).filter(Boolean);
  }
}

// Nothing to verify: return honestly rather than fabricating a verdict.
if (claims.length === 0) {
  return {
    surviving: [],
    refuted: [],
    revised_answer: rawAnswer || "No answer and no claims were provided, so there was nothing to verify.",
    residual_uncertainty: [
      rawAnswer
        ? "Claim extraction produced no load-bearing claims; the answer was passed through unverified."
        : "No input was provided to adversarial-verify."
    ],
    vote_summary: [],
    note: "No adversarial verification was performed. This is not a parity claim; see eval/parity-eval.md to actually measure parity."
  };
}

// ---- Refute phase: each claim flows independently through the pipeline. ----
// Stage 1 hands the claim forward (claims are already resolved); Stage 2 fans
// out `votersN` diverse skeptics in PARALLEL to refute it. Because the pipeline
// has no barrier between stages, each claim is refuted as soon as it is ready
// rather than waiting on the slowest claim.
phase("Refute");
log(`Refuting ${claims.length} claim(s) with ${votersN} independent skeptics each (ties break toward refuted).`);

const claimItems = claims.map((c, i) => ({ index: i, claim: c }));

const refutedRaw = await pipeline(
  claimItems,
  (item) => Promise.resolve(item),
  (item) =>
    parallel(
      Array.from({ length: votersN }, (_, vi) => {
        const angle = SKEPTIC_ANGLES[vi % SKEPTIC_ANGLES.length];
        return () =>
          agent(refutePrompt(item.claim, angle, vi), {
            schema: VOTE_SCHEMA,
            phase: "Refute",
            label: "refute:" + item.index + ":" + angle.key
          }).then((v) =>
            v || {
              refuted: true,
              reason: "skeptic agent did not return a verdict; counted as refuted per the default-under-uncertainty rule",
              confidence: "low",
              failed: true
            }
          );
      })
    ).then((votes) => ({ item, votes: votes || [] }))
);

// ---- Tally: a claim SURVIVES only if a strict majority fail to refute it. --
const evaluated = refutedRaw.filter(Boolean).map(({ item, votes }) => {
  // A dropped voter slot is treated as a refuting abstention (fail-closed).
  const votesArr = Array.isArray(votes) ? votes : [];
  const refutedVotes = votesArr.filter((v) => v && v.refuted === true).length;
  const missing = Math.max(0, votersN - votesArr.length);
  const refutedCount = refutedVotes + missing;
  const nonRefuted = votersN - refutedCount;
  const survives = nonRefuted * 2 > votersN; // strict majority; ties -> refuted
  const reasons = votesArr
    .filter((v) => v && v.refuted === true && typeof v.reason === "string")
    .map((v) => v.reason);
  return {
    claim: item.claim,
    index: item.index,
    survives,
    refuted_votes: refutedCount,
    non_refuted_votes: nonRefuted,
    total_votes: votersN,
    reasons
  };
});
// Report claims in their original order.
evaluated.sort((a, b) => a.index - b.index);

const survivingDetail = evaluated.filter((e) => e.survives);
const refutedDetail = evaluated.filter((e) => !e.survives);

const surviving = survivingDetail.map((e) => e.claim);
const refuted = refutedDetail.map((e) => ({ claim: e.claim, reasons: e.reasons }));

log(`${surviving.length} claim(s) survived; ${refuted.length} refuted.`);

// ---- Revise phase: rewrite the answer around what survived. ---------------
phase("Revise");
const revision = await agent(revisePrompt(rawAnswer, surviving, refuted), {
  schema: REVISE_SCHEMA,
  phase: "Revise",
  label: "revise"
});

// ---- Assemble return value (robust to a failed revise agent) --------------
const revised_answer = (revision && typeof revision.revised_answer === "string")
  ? revision.revised_answer
  : (rawAnswer
      ? rawAnswer + "\n\n[adversarial-verify: the revise step did not complete. Treat the following claims as REFUTED and disregard them: "
        + (refuted.map((r) => r.claim).join(" | ") || "(none)") + "]"
      : "Surviving claims only:\n- " + (surviving.join("\n- ") || "(none survived)"));

return {
  surviving,
  refuted,
  revised_answer,
  residual_uncertainty:
    (revision && Array.isArray(revision.residual_uncertainty))
      ? revision.residual_uncertainty
      : [],
  vote_summary: evaluated.map((e) => ({
    claim: e.claim,
    survives: e.survives,
    refuted_votes: e.refuted_votes,
    total_votes: e.total_votes
  })),
  note:
    "Adversarial self-check with " + votersN + " diverse skeptics per claim (default-refuted under uncertainty, ties break toward refuted). "
    + "This buys precision against confident-but-wrong claims but is NOT a measured parity benchmark; because the skeptics share the base model's weights, correlated blind spots can survive. See eval/parity-eval.md to actually measure parity."
};

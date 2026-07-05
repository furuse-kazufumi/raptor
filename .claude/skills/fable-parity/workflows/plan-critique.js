export const meta = {
  name: "plan-critique",
  description:
    "Planning-depth uplift for Opus: generate N candidate plans in parallel each under a DIFFERENT bias (MVP-first / risk-first / user-value-first / simplicity-first), score them with a diverse judge panel (one lens per judge), synthesize the winner while grafting the best ideas of the runners-up, then run an adversarial pre-mortem that attacks the final plan for edge cases, hidden dependencies, and ordering/failure modes and folds concrete fixes back in. Buys back Fable-tier look-ahead by externalizing the plan and critiquing it in fresh contexts; it does NOT invent capability the base model lacks and makes NO measured-parity claim.",
  phases: [
    { title: "Generate", detail: "Run `candidates` planner agents in parallel, each forced onto a DIFFERENT bias (MVP-first / risk-first / user-value-first / simplicity-first, cycled by index) so plans do not mode-collapse onto one framing. Each returns {steps, key_risks, assumptions}." },
    { title: "Judge", detail: "A panel of judge agents scores EVERY candidate. Each judge uses a DIFFERENT lens (feasibility / completeness / risk / simplicity, by index) and scores independently; diversity decorrelates individual biases. Scores are aggregated per plan." },
    { title: "Synthesize", detail: "One agent builds the FINAL plan from the top-scoring candidate while grafting the strongest ideas of the runners-up, and records what it grafted and why." },
    { title: "Stress", detail: "An adversarial agent runs a pre-mortem on the final plan — edge cases, hidden dependencies, wrong ordering, failure modes — and returns concrete fixes, which are folded back into the plan as hardening steps and mitigated risks." }
  ]
};

// ---- Inputs ---------------------------------------------------------------
// Accept args as an object, a JSON string, or a bare string (taken as the goal).
// The Workflow tool is meant to pass an object, but some callers stringify it.
const A = (function () {
  if (args && typeof args === "object") return args;
  if (typeof args === "string") {
    const s = args.trim();
    if (s.startsWith("{")) { try { return JSON.parse(s); } catch (_) { /* fall through */ } }
    return { goal: s };
  }
  return {};
})();
const goal = (typeof A.goal === "string" && A.goal.trim())
  ? A.goal.trim()
  : "(no goal provided)";
const constraints = (typeof A.constraints === "string" && A.constraints.trim())
  ? A.constraints.trim()
  : "";
const requestedCandidates = Number.isFinite(Number(A.candidates))
  ? Number(A.candidates)
  : 3;
// Clamp to a sane, budget-friendly range (Math.random is forbidden; Math.max/min are fine).
const candidatesN = Math.max(2, Math.min(6, Math.trunc(requestedCandidates) || 3));

// Diverse planning biases, varied by index so parallel planners cover more of the
// solution space instead of all landing on the first workable framing. Correlated-
// error mitigation: diversity of framing matters more than raw candidate count.
const BIASES = [
  {
    key: "MVP-first",
    guidance:
      "Bias: MVP-first. Design the SMALLEST plan that delivers a working, end-to-end slice of value fast. Cut scope aggressively, defer anything not on the critical path to a 'later' bucket, and prefer a thin vertical slice over a broad-but-incomplete build. State explicitly what you are deliberately leaving out."
  },
  {
    key: "risk-first",
    guidance:
      "Bias: risk-first. Identify the parts most likely to fail, block, or blow up the timeline, and sequence the plan to RETIRE those risks earliest (spikes, proofs, de-risking experiments up front). Front-load the scary unknowns; make each step reduce the biggest remaining uncertainty."
  },
  {
    key: "user-value-first",
    guidance:
      "Bias: user-value-first. Work backwards from the outcome the end user actually needs. Order steps by the value they unlock for the user, not by internal convenience, and make every step trace to a concrete user-visible benefit. Reject work that does not move a user outcome."
  },
  {
    key: "simplicity-first",
    guidance:
      "Bias: simplicity-first. Prefer the plan with the fewest moving parts, dependencies, and new concepts. Reuse existing pieces over building new ones, avoid speculative generality, and choose the boring, robust option every time there is a choice. Justify any complexity you keep."
  },
  {
    key: "throughput-first",
    guidance:
      "Bias: throughput-first. Maximize parallelizable, independently-shippable workstreams. Split the plan so multiple pieces can proceed at once without blocking each other, call out the true sequential bottlenecks, and minimize hand-off/merge friction between parallel tracks."
  },
  {
    key: "robustness-first",
    guidance:
      "Bias: robustness-first. Optimize for a plan that survives contact with reality: explicit failure handling, verification/rollback at each step, and no step that cannot be checked before the next depends on it. Prefer a slower plan that is hard to get wrong over a fast one that is fragile."
  }
];

// Judge lenses, one judge per lens (varied by index). A panel of diverse lenses
// is a better, cheaper selector than one generic judge and cuts intra-judge bias.
const LENSES = [
  {
    key: "feasibility",
    guidance:
      "Lens: FEASIBILITY. Can this plan actually be executed as written, in order, with the stated assumptions? Penalize steps that assume unavailable prerequisites, hand-wave the hard part, or depend on something produced later. Reward plans whose every step is concretely actionable."
  },
  {
    key: "completeness",
    guidance:
      "Lens: COMPLETENESS. Does the plan cover everything the goal requires, or are there gaps that will surface as surprise work? Penalize missing setup, missing verification, ignored constraints, and unaddressed parts of the goal. Reward plans that leave nothing decisive uncovered."
  },
  {
    key: "risk",
    guidance:
      "Lens: RISK. How well does the plan anticipate and contain what can go wrong? Penalize plans that leave the biggest risks unaddressed or retire them too late. Reward plans that front-load de-risking and have a fallback when a step fails."
  },
  {
    key: "simplicity",
    guidance:
      "Lens: SIMPLICITY. Is this the least-complex plan that still achieves the goal? Penalize unnecessary steps, speculative generality, and avoidable dependencies. Reward plans that reach the outcome with the fewest moving parts. Do not reward simplicity bought by dropping required scope."
  }
];

// ---- Schemas --------------------------------------------------------------
const PLAN_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    bias: { type: "string", description: "The planning bias you were assigned." },
    steps: { type: "array", items: { type: "string" }, description: "Ordered, concretely-actionable plan steps. Each step should be executable given the prior steps." },
    key_risks: { type: "array", items: { type: "string" }, description: "The risks this plan is most exposed to, most severe first." },
    assumptions: { type: "array", items: { type: "string" }, description: "Assumptions the plan rests on that, if false, would change it." }
  },
  required: ["steps", "key_risks", "assumptions"]
};

const JUDGE_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    lens: { type: "string", description: "The scoring lens you were assigned." },
    scores: {
      type: "array",
      description: "One entry per candidate plan you were shown.",
      items: {
        type: "object",
        additionalProperties: false,
        properties: {
          plan_index: { type: "integer", description: "The plan_index of the candidate being scored." },
          score: { type: "number", description: "Integer 1-5 on YOUR lens (1=poor, 3=adequate, 5=excellent). Score only your lens; ignore the others." },
          reason: { type: "string", description: "One or two sentences justifying the score with a specific, checkable observation about the plan." }
        },
        required: ["plan_index", "score", "reason"]
      }
    }
  },
  required: ["scores"]
};

const SYNTH_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    final_plan: {
      type: "object",
      additionalProperties: false,
      properties: {
        steps: { type: "array", items: { type: "string" }, description: "The final ordered plan steps, dependency-correct." },
        risks: { type: "array", items: { type: "string" }, description: "The consolidated key risks of the final plan." },
        assumptions: { type: "array", items: { type: "string" }, description: "The assumptions the final plan rests on." },
        rationale: { type: "string", description: "Why this plan, built from the top candidate plus grafts, is the strongest synthesis." }
      },
      required: ["steps", "risks", "assumptions", "rationale"]
    },
    graft_notes: {
      type: "array",
      items: { type: "string" },
      description: "Each note names a specific idea grafted from a runner-up plan (by bias) into the final plan, and why it improved on the top plan."
    }
  },
  required: ["final_plan", "graft_notes"]
};

const STRESS_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    stress_findings: {
      type: "array",
      description: "Concrete weaknesses found by attacking the final plan. Empty only if you genuinely found none after a real pre-mortem.",
      items: {
        type: "object",
        additionalProperties: false,
        properties: {
          category: {
            type: "string",
            enum: ["edge_case", "hidden_dependency", "ordering", "failure_mode", "missing_prerequisite", "other"],
            description: "What kind of weakness this is."
          },
          issue: { type: "string", description: "The specific weakness — a concrete scenario or dependency, not a vague concern." },
          severity: { type: "string", enum: ["low", "medium", "high", "critical"], description: "How badly this breaks the plan if unaddressed." },
          fix: { type: "string", description: "A concrete, actionable fix to fold into the plan (a new step, a reordering, or an added guard)." }
        },
        required: ["category", "issue", "severity", "fix"]
      }
    },
    residual_risk: { type: "string", description: "The most important risk that REMAINS even after all fixes are applied — stated honestly, not minimized." }
  },
  required: ["stress_findings"]
};

// ---- Prompt builders ------------------------------------------------------
const goalBlock = `\n\nGOAL:\n${goal}\n`;
const constraintsBlock = constraints ? `\nCONSTRAINTS (hard — every plan must respect these):\n${constraints}\n` : "\n";

function plannerPrompt(item) {
  return [
    "You are ONE independent planner among several drafting a plan for the SAME goal in parallel. You cannot see the others.",
    "Produce the best plan you can UNDER YOUR ASSIGNED BIAS. Commit to the bias even if another framing feels easier — the point is that the panel of plans covers different regions of the solution space.",
    "",
    `ASSIGNED BIAS: ${item.bias}`,
    item.guidance,
    "",
    "Discipline: plan far enough ahead that later steps are not blocked by unmet prerequisites; make ordering explicit; surface the assumptions your plan depends on rather than hiding them. Do not fabricate specifics (tools, APIs, file paths) you are not sure exist — if something must be verified, make verifying it a step.",
    constraintsBlock,
    goalBlock
  ].join("\n");
}

function judgePrompt(lens, plansForJudge) {
  return [
    "You are ONE judge on a panel scoring candidate plans for the goal below. You score ONLY on your assigned lens; other judges cover the other lenses.",
    "Score every candidate independently on a 1-5 integer scale (1=poor, 3=adequate, 5=excellent) FOR YOUR LENS ONLY. Do not reward a plan for being strong on a dimension that is not yours.",
    "Be a discerning grader: reserve 5 for genuinely excellent, and do not inflate. If uncertain, score toward the middle and say why. Base each score on a specific, checkable observation about the plan, not its tone.",
    "",
    `YOUR LENS: ${lens.key}`,
    lens.guidance,
    constraintsBlock,
    goalBlock,
    "",
    "CANDIDATE PLANS (score each by its plan_index):",
    JSON.stringify(plansForJudge, null, 2)
  ].join("\n");
}

function synthesizePrompt(rankedPlans, aggregated) {
  return [
    "You are synthesizing ONE final plan from several scored candidate plans, each drafted under a different bias.",
    "Method:",
    "1. Start from the TOP-scoring candidate as the backbone.",
    "2. Graft in the strongest specific ideas from the runner-up plans where they cover a gap or beat the backbone — especially risk-handling, missing prerequisites, and simpler alternatives. Name each graft in graft_notes.",
    "3. Fix ordering so no step depends on something produced later; insert any prerequisite the candidates missed.",
    "4. Respect every hard constraint. Do NOT invent steps, tools, or dependencies that no candidate proposed and that you cannot justify — if a needed piece is unknown, make verifying/obtaining it an explicit step instead of fabricating specifics.",
    "5. Consolidate risks and assumptions across the grafted plan honestly; do not average away a real risk just because only one candidate raised it.",
    constraintsBlock,
    goalBlock,
    "",
    "AGGREGATED JUDGE SCORES (higher mean = better; per-lens detail included):",
    JSON.stringify(aggregated, null, 2),
    "",
    "CANDIDATE PLANS, RANKED BEST-FIRST:",
    JSON.stringify(rankedPlans, null, 2)
  ].join("\n");
}

function stressPrompt(finalPlan) {
  return [
    "You are an ADVERSARIAL reviewer running a PRE-MORTEM on the final plan below, in a clean context. You did not write it and you owe it no charity.",
    "Assume it is six steps into execution and something has gone wrong. Your job is to find WHY, before it happens:",
    "- edge_case: inputs/conditions the plan does not handle.",
    "- hidden_dependency: something a step silently relies on that is not guaranteed by an earlier step.",
    "- ordering: a step that runs before its prerequisite is ready.",
    "- missing_prerequisite: setup/verification the plan omits.",
    "- failure_mode: a step that can fail with no detection or fallback.",
    "Rules: every finding must be a CONCRETE scenario, not a vague worry, and must carry an actionable fix (a new step, a reordering, or a guard). If you are uncertain whether something is a real gap, report it as low/medium rather than assuming it is fine — but do not invent flaws that are not there. Then state the single most important risk that REMAINS after all your fixes are applied.",
    goalBlock,
    "",
    "FINAL PLAN TO ATTACK:",
    JSON.stringify(finalPlan, null, 2)
  ].join("\n");
}

// ---- Phase 1: Generate (parallel, bias varied by index) -------------------
phase("Generate");
log(`Drafting ${candidatesN} candidate plans in parallel, each under a distinct bias.`);

const planItems = [];
for (let i = 0; i < candidatesN; i++) {
  const b = BIASES[i % BIASES.length];
  planItems.push({ index: i, bias: b.key, guidance: b.guidance });
}

const plansRaw = await parallel(
  planItems.map((it) => () =>
    agent(plannerPrompt(it), {
      schema: PLAN_SCHEMA,
      phase: "Generate",
      label: "plan:" + it.bias
    }).then((p) =>
      p
        ? {
            plan_index: it.index,
            bias: it.bias,
            steps: Array.isArray(p.steps) ? p.steps : [],
            key_risks: Array.isArray(p.key_risks) ? p.key_risks : [],
            assumptions: Array.isArray(p.assumptions) ? p.assumptions : []
          }
        : null
    )
  )
);

const plans = plansRaw.filter(Boolean);
log(`Generated ${plans.length}/${candidatesN} candidate plans.`);

// Honest early-out: no plans survived generation.
if (plans.length === 0) {
  return {
    final_plan: null,
    graft_notes: [],
    stress_findings: [],
    note: "All planner agents failed; no candidate plan was produced. No plan is returned and no parity claim is made. Re-run or escalate."
  };
}

const validIndices = new Set(plans.map((p) => p.plan_index));

// ---- Phase 2: Judge (panel, one lens per judge, scores every plan) --------
phase("Judge");
log(`Scoring plans with a ${LENSES.length}-lens judge panel.`);

const plansForJudge = plans.map((p) => ({
  plan_index: p.plan_index,
  bias: p.bias,
  steps: p.steps,
  key_risks: p.key_risks,
  assumptions: p.assumptions
}));

const judgesRaw = await parallel(
  LENSES.map((lens) => () =>
    agent(judgePrompt(lens, plansForJudge), {
      schema: JUDGE_SCHEMA,
      phase: "Judge",
      label: "judge:" + lens.key
    }).then((j) => (j ? { lens: lens.key, scores: Array.isArray(j.scores) ? j.scores : [] } : null))
  )
);

const judges = judgesRaw.filter(Boolean);

// Aggregate scores per plan_index (only for plans that actually exist).
const aggMap = new Map();
for (const j of judges) {
  for (const s of j.scores) {
    if (!s || !Number.isFinite(Number(s.plan_index))) continue;
    const pi = Math.trunc(Number(s.plan_index));
    if (!validIndices.has(pi)) continue;
    const sc = Number(s.score);
    if (!Number.isFinite(sc)) continue;
    if (!aggMap.has(pi)) aggMap.set(pi, { plan_index: pi, total: 0, count: 0, per_lens: [] });
    const e = aggMap.get(pi);
    e.total += sc;
    e.count += 1;
    e.per_lens.push({ lens: j.lens, score: sc, reason: s.reason || "" });
  }
}
for (const e of aggMap.values()) {
  e.mean = e.count > 0 ? e.total / e.count : null;
}

log(`Panel returned ${judges.length}/${LENSES.length} judge sheets; ${aggMap.size} plans scored.`);

// Attach aggregates and rank best-first. Plans without any score keep original order after scored ones.
const plansScored = plans.map((p) => {
  const a = aggMap.get(p.plan_index) || null;
  return { ...p, mean: a ? a.mean : null, score_count: a ? a.count : 0, per_lens: a ? a.per_lens : [] };
});

const ranked = plansScored.slice().sort((a, b) => {
  const am = a.mean === null ? -Infinity : a.mean;
  const bm = b.mean === null ? -Infinity : b.mean;
  if (bm !== am) return bm - am;
  if (b.score_count !== a.score_count) return b.score_count - a.score_count;
  return a.plan_index - b.plan_index;
});

const aggregatedForSynth = ranked.map((p) => ({
  plan_index: p.plan_index,
  bias: p.bias,
  mean_score: p.mean,
  score_count: p.score_count,
  per_lens: p.per_lens
}));

// ---- Phase 3: Synthesize --------------------------------------------------
phase("Synthesize");
log(`Synthesizing the final plan from the top candidate (${ranked[0].bias}) with grafts from the runners-up.`);

const rankedForSynth = ranked.map((p) => ({
  plan_index: p.plan_index,
  bias: p.bias,
  mean_score: p.mean,
  steps: p.steps,
  key_risks: p.key_risks,
  assumptions: p.assumptions
}));

const synthesis = await agent(synthesizePrompt(rankedForSynth, aggregatedForSynth), {
  schema: SYNTH_SCHEMA,
  phase: "Synthesize",
  label: "synthesize"
});

// Build the working final plan, with an honest fallback if synthesis failed.
let finalPlan;
let graftNotes;
if (synthesis && synthesis.final_plan) {
  const fp = synthesis.final_plan;
  finalPlan = {
    steps: Array.isArray(fp.steps) ? fp.steps.slice() : [],
    risks: Array.isArray(fp.risks) ? fp.risks.slice() : [],
    assumptions: Array.isArray(fp.assumptions) ? fp.assumptions.slice() : [],
    rationale: typeof fp.rationale === "string" ? fp.rationale : ""
  };
  graftNotes = Array.isArray(synthesis.graft_notes) ? synthesis.graft_notes : [];
} else {
  // Fallback: return the top-ranked candidate unmerged, labelled honestly.
  const top = ranked[0];
  finalPlan = {
    steps: top.steps.slice(),
    risks: top.key_risks.slice(),
    assumptions: top.assumptions.slice(),
    rationale:
      "Synthesis step did not complete; returning the top-ranked candidate plan (" +
      top.bias +
      ") unmerged. Treat as provisional — no grafting or cross-plan reconciliation was applied."
  };
  graftNotes = [];
  log("Synthesis agent failed; falling back to the top-ranked candidate plan unmerged.");
}

// ---- Phase 4: Stress (adversarial pre-mortem, fold fixes back in) ---------
phase("Stress");
log("Running an adversarial pre-mortem on the final plan and folding fixes back in.");

const stress = await agent(stressPrompt(finalPlan), {
  schema: STRESS_SCHEMA,
  phase: "Stress",
  label: "stress"
});

const stressFindings = stress && Array.isArray(stress.stress_findings) ? stress.stress_findings : [];

// Deterministically fold the fixes into the final plan:
//  - every finding's fix becomes a mitigated risk entry, most-severe first;
//  - high/critical structural gaps (ordering/dependency/prerequisite) are ALSO
//    prepended as explicit hardening steps so they are addressed before execution.
const severityRank = { critical: 0, high: 1, medium: 2, low: 3 };
const structuralCats = new Set(["ordering", "hidden_dependency", "missing_prerequisite"]);

const sortedFindings = stressFindings
  .slice()
  .sort((a, b) => (severityRank[a && a.severity] ?? 4) - (severityRank[b && b.severity] ?? 4));

const foldedRisks = [];
const hardeningSteps = [];
for (const f of sortedFindings) {
  if (!f || typeof f.issue !== "string") continue;
  const sev = f.severity || "unrated";
  const cat = f.category || "other";
  const fix = typeof f.fix === "string" ? f.fix : "(no fix proposed)";
  foldedRisks.push(`[stress:${sev}/${cat}] ${f.issue} — mitigation: ${fix}`);
  if (structuralCats.has(cat) && (f.severity === "high" || f.severity === "critical")) {
    hardeningSteps.push(`Before execution, address ${cat} (${sev}): ${fix}`);
  }
}

if (hardeningSteps.length > 0) {
  finalPlan.steps = hardeningSteps.concat(finalPlan.steps);
}
if (foldedRisks.length > 0) {
  finalPlan.risks = finalPlan.risks.concat(foldedRisks);
}
if (stress && typeof stress.residual_risk === "string" && stress.residual_risk.trim()) {
  finalPlan.assumptions = finalPlan.assumptions.concat([
    "Residual risk after hardening (from pre-mortem): " + stress.residual_risk.trim()
  ]);
}

log(
  `Folded ${foldedRisks.length} stress fix(es) into the plan (` +
    `${hardeningSteps.length} as up-front hardening steps).`
);

// ---- Return ---------------------------------------------------------------
// Honest attribution: this returns an orchestration-hardened plan. It buys
// planning depth via externalize-then-critique; it does not create capability
// the base model lacks, and it makes NO claim of measured Fable/Opus parity.
return {
  final_plan: finalPlan,
  graft_notes: graftNotes,
  stress_findings: stressFindings,
  candidates_scored: aggregatedForSynth.map((a) => ({
    bias: a.bias,
    mean_score: a.mean_score,
    score_count: a.score_count
  })),
  residual_risk: stress && typeof stress.residual_risk === "string" ? stress.residual_risk : ""
};

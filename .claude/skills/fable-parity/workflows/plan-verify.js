export const meta = {
  name: "plan-verify",
  description:
    "High-assurance planning uplift for Opus: run plan-critique to produce a vetted plan, then adversarially VERIFY the load-bearing ASSUMPTIONS the plan silently depends on (feature exists, API supports X, migration is reversible, dependency is available, the constraint is really N) against PRIMARY / independent evidence — because a plan's internal pre-mortem shares the model's belief that its own assumptions are true. Refuted assumptions become blockers / plan changes; uncertain ones become explicit 'validate-before-starting' steps. Composes plan-critique with adversarial-verify. Buys back Fable-grade planning depth AND external grounding by spending orchestration; it is NOT a measured parity benchmark and cannot verify an assumption no evidence bears on (those stay UNCERTAIN, not CONFIRMED).",
  phases: [
    { title: "Plan", detail: "Run the shipped plan-critique workflow (composed via workflow()) to get a vetted, stress-tested plan. Falls back to an inline planner if the nested run is unavailable or empty." },
    { title: "Assume", detail: "Extract the load-bearing ASSUMPTIONS the plan depends on — the factual / feasibility claims that, if false, would break or reorder the plan — prioritising the checkable, plan-breaking ones." },
    { title: "Verify", detail: "For each assumption, independent skeptics (with web/tool access) try to REFUTE it against PRIMARY or independent evidence, defaulting to refuted/uncertain when it is unverifiable or only self-asserted. Majority sets the status." },
    { title: "Harden", detail: "Fold verdicts back into the plan: refuted assumptions force a plan change / blocker; uncertain assumptions become explicit 'validate before proceeding' steps placed early; confirmed ones pass. Return the hardened plan + an assumption ledger + residual risks." }
  ]
};

// ---- Inputs ---------------------------------------------------------------
// Accept args as an object, a JSON string, or a bare string (taken as the goal).
const A = (function () {
  if (args && typeof args === "object") return args;
  if (typeof args === "string") {
    const s = args.trim();
    if (s.startsWith("{")) { try { return JSON.parse(s); } catch (_) { /* fall through */ } }
    return { goal: s };
  }
  return {};
})();

const hasGoal = !!(typeof A.goal === "string" && A.goal.trim());
const goal = hasGoal ? A.goal.trim() : "(no goal provided)";
const constraints = (typeof A.constraints === "string" && A.constraints.trim()) ? A.constraints.trim() : "";
const candidatesN = Math.max(2, Math.min(6, Math.trunc(Number(A.candidates)) || 3));
const votersN = Math.max(1, Math.min(4, Math.trunc(Number(A.voters)) || 2));
const maxAssumptions = Math.max(3, Math.min(10, Math.trunc(Number(A.max_assumptions)) || 6));

// Independent non-Opus cross-check of the assumptions (OpenAI Codex via ext_verify).
// The Opus skeptics here already ground in retrieved primary sources, so this is a
// SECONDARY, downgrade-only signal: an external refutation can knock a 'confirmed'
// down to 'uncertain' (a different family disputes it), but the tool-less external
// verifier's 'survives' NEVER upgrades a verdict. Default ON, fully degrading.
const externalVerify = A.external_verify !== false && String(A.external_verify).toLowerCase() !== "off";
const EXT_VERIFY_PATH = "D:/tools/raptor/.claude/skills/fable-parity/bin/ext_verify.py";

// Sibling plan workflow, composed via workflow(). Absolute path (the skill's docs
// hardcode this machine's paths too); if unreachable the try/catch degrades to an
// inline planner rather than failing the whole run.
const PLAN = "D:/tools/raptor/.claude/skills/fable-parity/workflows/plan-critique.js";

const HONESTY =
  "Plan-then-verify: plan-critique produces the plan, then its load-bearing assumptions are checked against external/primary evidence. Recovers planning depth AND grounding by spending orchestration; it is not a measured parity benchmark. CONFIRMED means evidence was found, not certainty; assumptions no evidence bears on are marked UNCERTAIN (validate before relying on them), never CONFIRMED.";

const TOOL_NOTE =
  "TOOL ACCESS: web/other tools are NOT preloaded. First call ToolSearch to load one, then call it. " +
  "Search: ToolSearch query \"select:firecrawl_search\" (preferred) or \"select:WebSearch\". " +
  "Open a page: ToolSearch query \"select:WebFetch\" or \"select:firecrawl_scrape\". Only cite URLs a real tool returned.";

// ---- Guard: no goal -> fail fast, spawn nothing ---------------------------
if (!hasGoal) {
  return {
    verified_plan: { steps: [], risks: [], validate_before_starting: [], rationale: "No goal was provided; nothing to plan." },
    assumption_ledger: [],
    residual_risks: [],
    confidence: "low",
    notes: HONESTY
  };
}

// ---- Schemas --------------------------------------------------------------
const PLAN_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    steps: { type: "array", items: { type: "string" } },
    key_risks: { type: "array", items: { type: "string" } },
    assumptions: { type: "array", items: { type: "string" } }
  },
  required: ["steps"]
};

const ASSUMPTIONS_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    assumptions: {
      type: "array",
      description: "The load-bearing assumptions the plan depends on — factual/feasibility claims that, if false, break or reorder the plan.",
      items: {
        type: "object",
        additionalProperties: false,
        properties: {
          id: { type: "string" },
          assumption: { type: "string" },
          why: { type: "string", description: "what in the plan breaks if this is false" },
          checkable: { type: "boolean", description: "true if external/primary evidence could confirm or refute it; false if it is an internal/project fact only the user knows" }
        },
        required: ["id", "assumption"]
      }
    }
  },
  required: ["assumptions"]
};

const VERDICT_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    verdict: { type: "string", enum: ["confirmed", "refuted", "uncertain"] },
    reasoning: { type: "string" },
    evidence: { type: "string", description: "the specific independent/primary evidence found (quote or precise fact)" },
    sources: { type: "array", items: { type: "string" }, description: "independent/primary source URLs actually retrieved" }
  },
  required: ["verdict", "reasoning"]
};

const REPORT_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    verified_plan: {
      type: "object",
      additionalProperties: false,
      properties: {
        summary: { type: "string" },
        steps: { type: "array", items: { type: "string" } },
        risks: { type: "array", items: { type: "string" } },
        validate_before_starting: { type: "array", items: { type: "string" }, description: "actions to confirm UNCERTAIN/REFUTED assumptions before committing" },
        rationale: { type: "string" }
      },
      required: ["steps"]
    },
    assumption_ledger: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        properties: {
          assumption: { type: "string" },
          status: { type: "string", enum: ["confirmed", "refuted", "uncertain"] },
          note: { type: "string" },
          sources: { type: "array", items: { type: "string" } }
        },
        required: ["assumption", "status"]
      }
    },
    residual_risks: { type: "array", items: { type: "string" } },
    confidence: { type: "string", enum: ["low", "medium", "high"] }
  },
  required: ["verified_plan", "assumption_ledger", "confidence"]
};

// External relay: one dispatch that cross-checks every assumption with the non-Opus
// family via ext_verify.py. Short assumption strings are safe as shell args.
const EXT_RELAY_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    results: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        properties: {
          id: { type: "string" },
          verdict: { type: "string", enum: ["survives", "refuted", "unverified"] },
          reason: { type: "string" },
          ok: { type: "boolean" }
        },
        required: ["id", "verdict", "ok"]
      }
    }
  },
  required: ["results"]
};

function extRelayPrompt(assms) {
  const numbered = assms.map((a) => `id ${a.id}: ${a.assumption}`).join("\n");
  return [
    "You relay to an EXTERNAL non-Opus verifier (different model family) to cross-check a plan's assumptions. For EACH assumption below, run this EXACT command with the Bash tool, substituting the assumption text for <CLAIM> (escape embedded quotes so the command stays valid):",
    "",
    "  py -3.11 \"" + EXT_VERIFY_PATH + "\" --model codex --claim \"<CLAIM>\" --context \"plan goal: " + goal.replace(/"/g, "'").slice(0, 200) + "\" --timeout 180",
    "",
    "Each run prints ONE JSON line {\"model\":\"codex\",\"verdict\":\"survives\"|\"refuted\",\"reason\":\"...\",\"ok\":true}. Use EXACTLY what it prints; never invent a verdict. On error/ok:false, record it as printed.",
    "",
    "ASSUMPTIONS:",
    numbered,
    "",
    "Return { results: [ {id, verdict, reason, ok}, ... ] } with one entry per assumption id."
  ].join("\n");
}

// ---- Helpers --------------------------------------------------------------
function planIsEmpty(plan) {
  const fp = plan && plan.final_plan;
  if (!fp) return true;
  if (!Array.isArray(fp.steps) || fp.steps.length === 0) return true;
  return false;
}

async function miniPlan() {
  const p = await agent(
    "Produce a concrete, ordered implementation plan for the goal below. Give numbered steps with prerequisites, the key risks, and — importantly — the load-bearing ASSUMPTIONS the plan depends on (facts/feature-availability/feasibility that, if false, would break it).\n\nGOAL: " + goal + (constraints ? "\nCONSTRAINTS: " + constraints : ""),
    { schema: PLAN_SCHEMA, phase: "Plan", label: "mini-plan" }
  );
  return { final_plan: { steps: (p && p.steps) || [], risks: (p && p.key_risks) || [], assumptions: (p && p.assumptions) || [], rationale: "inline mini-plan fallback" }, stress_findings: [], residual_risk: [] };
}

function extractPrompt(plan) {
  const fp = plan.final_plan || {};
  return [
    "Extract the load-bearing ASSUMPTIONS this plan depends on — the factual / feasibility claims that, if FALSE, would break the plan, force a reorder, or add unplanned work. These are what a plan's own pre-mortem tends to MISS because the planner believes them.",
    "GOAL: " + goal + (constraints ? "\nCONSTRAINTS: " + constraints : ""),
    "",
    "PLAN STEPS:",
    JSON.stringify(fp.steps || [], null, 2),
    "PLAN'S SELF-LISTED ASSUMPTIONS (start here, then mine the steps for IMPLICIT ones):",
    JSON.stringify(fp.assumptions || [], null, 2),
    "PLAN RISKS:",
    JSON.stringify(fp.risks || [], null, 2),
    "",
    "Return up to " + Math.min(maxAssumptions, 8) + " single, checkable assumptions, prioritising the ones that are BOTH plan-breaking if false AND externally checkable (feature/API exists, library supports X, operation is reversible, version/limit is N). Mark checkable=false for internal/project facts only the user knows (team size, budget, existing infra)."
  ].join("\n");
}

function verifyPrompt(assumption, angleIdx) {
  const angles = [
    "Find the PRIMARY source (official docs, the library's own code/release notes, a standard/spec, or the first-party site) and check the assumption directly. Quote the exact fact.",
    "Look for INDEPENDENT evidence that the assumption is FALSE or more limited than stated (known limitations, breaking changes, unsupported combinations, gotchas). Absence of support = uncertain, not confirmed.",
    "Attack the specifics (version, limit, 'supported', 'reversible', 'available'): is the assumption exactly right, or is a plausible-but-wrong detail load-bearing?"
  ];
  return [
    "You are a skeptic checking a PLAN's assumption. Try to REFUTE the assumption below. Default to \"refuted\" or \"uncertain\" if you cannot find solid primary/independent support. Confirm ONLY if primary/independent evidence clearly backs it. If the assumption is an internal/project fact you cannot check externally, return \"uncertain\" (it must be validated by the user).",
    "PLAN GOAL: " + goal,
    "",
    "ASSUMPTION TO CHECK: " + assumption.assumption,
    (assumption.checkable === false ? "(The extractor marked this as an internal/project fact — likely UNCERTAIN unless you find external evidence.)" : ""),
    "",
    "Verification angle for THIS check: " + angles[angleIdx % angles.length],
    "",
    TOOL_NOTE,
    "",
    "Return your verdict (confirmed / refuted / uncertain), the specific evidence, and the source URLs you actually retrieved."
  ].join("\n");
}

function hardenPrompt(plan, graded) {
  return [
    "Fold the assumption-verification verdicts back into a HARDENED plan. Be honest: where an assumption was REFUTED, the plan MUST change (add a step to handle the now-false assumption, pick a different approach, or reorder); where UNCERTAIN, add an explicit 'validate before proceeding' item placed EARLY so the plan de-risks it first; where CONFIRMED, it passes.",
    "GOAL: " + goal + (constraints ? "\nCONSTRAINTS: " + constraints : ""),
    "",
    "VETTED PLAN (from plan-critique):",
    JSON.stringify(plan.final_plan || {}, null, 2),
    "PLAN-CRITIQUE STRESS FINDINGS (already folded in once):",
    JSON.stringify(plan.stress_findings || [], null, 2),
    "",
    "ASSUMPTION VERIFICATION RESULTS:",
    JSON.stringify(graded, null, 2),
    "",
    "Produce: verified_plan (steps reflecting the verdicts; a validate_before_starting list for the uncertain/refuted assumptions; risks; rationale), an assumption_ledger (assumption + status + note + sources), residual_risks, and an overall confidence reflecting how many load-bearing assumptions survived independent verification. Never claim measured parity."
  ].join("\n");
}

// ---- Run ------------------------------------------------------------------
phase("Plan");
log("plan-verify (candidates=" + candidatesN + ", voters=" + votersN + "): building a vetted plan, then verifying its load-bearing assumptions.");

let plan;
try {
  plan = await workflow({ scriptPath: PLAN }, { goal, constraints, candidates: candidatesN });
  if (planIsEmpty(plan)) {
    log("Nested plan empty/degenerate — running inline mini-plan fallback.");
    plan = await miniPlan();
  }
} catch (e) {
  log("workflow() compose failed (" + (e && e.message) + ") — inline mini-plan fallback.");
  plan = await miniPlan();
}

phase("Assume");
let extracted = null;
try {
  extracted = await agent(extractPrompt(plan), { schema: ASSUMPTIONS_SCHEMA, phase: "Assume", label: "extract-assumptions" });
} catch (e) {
  // Schema-retry-cap failures throw; catch so extraction failure degrades to
  // "return the vetted plan unverified" rather than killing the run.
  log("Assumption-extraction agent errored (" + (e && e.message) + "); returning the plan unverified.");
}
const assumptions = (extracted && Array.isArray(extracted.assumptions)) ? extracted.assumptions.slice(0, maxAssumptions) : [];

if (assumptions.length === 0) {
  return {
    verified_plan: {
      steps: (plan.final_plan && plan.final_plan.steps) || [],
      risks: (plan.final_plan && plan.final_plan.risks) || [],
      validate_before_starting: ["No load-bearing assumptions were extracted for verification; the plan above is UNVERIFIED — sanity-check its assumptions before committing."],
      rationale: (plan.final_plan && plan.final_plan.rationale) || ""
    },
    assumption_ledger: [],
    residual_risks: (plan.residual_risk || []),
    confidence: "low",
    plan_meta: { candidates: candidatesN, stress_findings: (plan.stress_findings || []).length },
    notes: HONESTY
  };
}

phase("Verify");
log("Verifying " + assumptions.length + " load-bearing assumption(s) with " + votersN + " Opus skeptic(s) each" + (externalVerify ? " + 1 independent non-Opus cross-check" : "") + ".");

// External non-Opus cross-check (one relay dispatch over all assumptions), run
// concurrently with the Opus skeptics. Degrades to an empty map on any failure.
const extPromise = (externalVerify && assumptions.length > 0)
  ? (async () => {
      try {
        const r = await agent(extRelayPrompt(assumptions), { schema: EXT_RELAY_SCHEMA, phase: "Verify", label: "ext-verify:codex" });
        const map = {};
        for (const x of ((r && r.results) || [])) if (x && x.id) map[x.id] = x;
        return map;
      } catch (e) {
        log("External assumption cross-check errored (" + (e && e.message) + "); Opus-only verification.");
        return {};
      }
    })()
  : Promise.resolve({});

const gradedPromise = parallel(
  assumptions.map((a) => () =>
    parallel(Array.from({ length: votersN }, (_v, ai) => () =>
      agent(verifyPrompt(a, ai), { schema: VERDICT_SCHEMA, agentType: "general-purpose", phase: "Verify", label: "verify:" + a.id + ":" + ai })
    )).then((votes) => {
      const v = votes.filter(Boolean);
      const conf = v.filter((x) => x.verdict === "confirmed").length;
      const ref = v.filter((x) => x.verdict === "refuted").length;
      let status = "uncertain";
      if (ref > conf) status = "refuted";
      else if (conf > 0 && ref === 0) status = "confirmed";
      const srcs = [];
      for (const x of v) for (const s of (x.sources || [])) srcs.push(s);
      return { id: a.id, assumption: a.assumption, status, checkable: a.checkable !== false, votes: v, sources: [...new Set(srcs)] };
    })
  )
);

const [gradedRaw, extMap] = await Promise.all([gradedPromise, extPromise]);
// Merge: downgrade-only. External refutation of a 'confirmed' -> 'uncertain' (an
// independent family disputes it); external 'survives' never upgrades. Record dissent.
const gradedClean = gradedRaw.filter(Boolean).map((g) => {
  const ext = extMap[g.id];
  const extUsable = !!(ext && ext.ok);
  const extRefuted = extUsable && ext.verdict === "refuted";
  let status = g.status;
  let externalDissent = false;
  if (extRefuted && status === "confirmed") { status = "uncertain"; externalDissent = true; }
  return { ...g, status, external: ext ? { verdict: ext.verdict, reason: ext.reason || "", usable: extUsable, model: "codex" } : { usable: false }, external_dissent: externalDissent };
});

phase("Harden");
let report = null;
try {
  report = await agent(hardenPrompt(plan, gradedClean), { schema: REPORT_SCHEMA, phase: "Harden", label: "harden" });
} catch (e) {
  log("Harden-synthesis agent errored (" + (e && e.message) + "); returning the vetted plan + raw assumption verdicts.");
}

if (report) {
  return {
    verified_plan: report.verified_plan,
    assumption_ledger: report.assumption_ledger || [],
    residual_risks: report.residual_risks || [],
    confidence: report.confidence || "low",
    verification: gradedClean.map((g) => ({ assumption: g.assumption, status: g.status, sources: g.sources })),
    plan_meta: { candidates: candidatesN, stress_findings: (plan.stress_findings || []).length },
    notes: HONESTY
  };
}

// Fallback: harden synthesis failed — return the vetted plan + raw assumption verdicts.
return {
  verified_plan: {
    steps: (plan.final_plan && plan.final_plan.steps) || [],
    risks: (plan.final_plan && plan.final_plan.risks) || [],
    validate_before_starting: gradedClean.filter((g) => g.status !== "confirmed").map((g) => "Validate: " + g.assumption + " (" + g.status + ")"),
    rationale: (plan.final_plan && plan.final_plan.rationale) || ""
  },
  assumption_ledger: gradedClean.map((g) => ({ assumption: g.assumption, status: g.status, sources: g.sources })),
  residual_risks: (plan.residual_risk || []),
  confidence: "low",
  plan_meta: { candidates: candidatesN, stress_findings: (plan.stress_findings || []).length },
  notes: HONESTY
};

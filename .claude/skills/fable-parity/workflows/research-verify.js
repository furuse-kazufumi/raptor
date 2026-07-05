export const meta = {
  name: "research-verify",
  description:
    "High-assurance research uplift for Opus: run the research-synthesize sweep, then adversarially VERIFY the answer's load-bearing claims against PRIMARY / independent sources before trusting them. Composes research-synthesize (breadth + citations) with adversarial-verify (refute-by-default skepticism), and returns each load-bearing claim graded CONFIRMED / REFUTED / UNCERTAIN with independent evidence. Use when a research answer will be acted on and a cited-but-unverified synthesis is not enough. It buys back Fable-grade thoroughness AND self-checking by spending orchestration; it is NOT a measured parity benchmark and cannot confirm a claim no primary source supports.",
  phases: [
    { title: "Research", detail: "Run the shipped research-synthesize workflow (composed via workflow()) to gather cited sources and a first synthesis. Falls back to an inline mini-sweep if the nested run is unavailable or returns a degenerate answer." },
    { title: "Extract", detail: "Pull the load-bearing factual claims out of the research answer — the ones that, if false, would change the conclusion." },
    { title: "Verify", detail: "For each claim, independent skeptics (with web access) try to REFUTE it using PRIMARY or independent sources, defaulting to refuted/uncertain when support is only self-published. Majority sets the claim's status." },
    { title: "Report", detail: "Grade every claim CONFIRMED / REFUTED / UNCERTAIN, fold the verdicts back into a corrected answer, list remaining open questions, and set a confidence that reflects how much survived independent verification." }
  ]
};

// ---- Inputs ---------------------------------------------------------------
// Accept args as an object, a JSON string, or a bare string (taken as the question).
const A = (function () {
  if (args && typeof args === "object") return args;
  if (typeof args === "string") {
    const s = args.trim();
    if (s.startsWith("{")) { try { return JSON.parse(s); } catch (_) { /* fall through */ } }
    return { question: s };
  }
  return {};
})();

const hasQuestion = !!(typeof A.question === "string" && A.question.trim());
const question = hasQuestion ? A.question.trim() : "(no research question provided)";

const depthRaw = (typeof A.depth === "string") ? A.depth.trim().toLowerCase() : "standard";
const depth = (depthRaw === "quick" || depthRaw === "standard" || depthRaw === "deep") ? depthRaw : "standard";

const votersN = Math.max(1, Math.min(4, Math.trunc(Number(A.voters)) || 2));
const maxClaims = Math.max(3, Math.min(10, Math.trunc(Number(A.max_claims)) || 6));

// Independent non-Opus cross-check of the claims (OpenAI Codex via ext_verify). The
// Opus skeptics here already ground in retrieved primary sources, so this is a
// SECONDARY, downgrade-only signal: an external refutation can knock a 'confirmed'
// down to 'uncertain'; the tool-less external verifier's 'survives' NEVER upgrades.
// Default ON, fully degrading.
const externalVerify = A.external_verify !== false && String(A.external_verify).toLowerCase() !== "off";
const EXT_VERIFY_PATH = "D:/tools/raptor/.claude/skills/fable-parity/bin/ext_verify.py";

// Sibling research workflow, composed via workflow(). Absolute path (the skill's
// docs hardcode this machine's paths too); if it is unreachable the try/catch
// below degrades to an inline mini-research rather than failing the whole run.
const RESEARCH = "D:/tools/raptor/.claude/skills/fable-parity/workflows/research-synthesize.js";

const HONESTY =
  "Research-then-verify over web/primary sources. Recovers thoroughness AND self-checking by spending orchestration; it is not ground truth and not a measured parity benchmark. A claim marked CONFIRMED means an independent/primary source was found, not that it is certainly true.";

const TOOL_NOTE =
  "TOOL ACCESS: web tools are NOT preloaded. First call ToolSearch to load one, then call it. " +
  "Search: ToolSearch query \"select:firecrawl_search\" (preferred) or \"select:WebSearch\". " +
  "Open a page: ToolSearch query \"select:WebFetch\" or \"select:firecrawl_scrape\". Only cite URLs a real tool returned.";

// ---- Guard: no question -> fail fast, spawn nothing ------------------------
if (!hasQuestion) {
  return {
    answer: "No research question was provided; nothing to research.",
    graded_claims: [],
    open_questions: ["Supply a concrete question in args.question and re-run."],
    confidence: "low",
    notes: HONESTY
  };
}

// ---- Schemas --------------------------------------------------------------
const CLAIMS_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    claims: {
      type: "array",
      description: "The load-bearing factual claims the answer depends on. Each a single, checkable statement.",
      items: {
        type: "object",
        additionalProperties: false,
        properties: {
          id: { type: "string" },
          claim: { type: "string" },
          why: { type: "string", description: "why it is load-bearing / what breaks if false" }
        },
        required: ["id", "claim"]
      }
    }
  },
  required: ["claims"]
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
    answer: { type: "string", description: "the corrected, verification-aware final answer" },
    graded_claims: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        properties: {
          claim: { type: "string" },
          status: { type: "string", enum: ["confirmed", "refuted", "uncertain"] },
          note: { type: "string" },
          sources: { type: "array", items: { type: "string" } }
        },
        required: ["claim", "status"]
      }
    },
    open_questions: { type: "array", items: { type: "string" } },
    confidence: { type: "string", enum: ["low", "medium", "high"] }
  },
  required: ["answer", "graded_claims", "open_questions", "confidence"]
};

// External relay: one dispatch that cross-checks every claim with the non-Opus family.
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

function extRelayPrompt(cls) {
  const numbered = cls.map((c) => `id ${c.id}: ${c.claim}`).join("\n");
  return [
    "You relay to an EXTERNAL non-Opus verifier (different model family) to cross-check a research answer's load-bearing claims. For EACH claim below, run this EXACT command with the Bash tool, substituting the claim text for <CLAIM> (escape embedded quotes so the command stays valid):",
    "",
    "  py -3.11 \"" + EXT_VERIFY_PATH + "\" --model codex --claim \"<CLAIM>\" --context \"research question: " + question.replace(/"/g, "'").slice(0, 200) + "\" --timeout 180",
    "",
    "Each run prints ONE JSON line {\"model\":\"codex\",\"verdict\":\"survives\"|\"refuted\",\"reason\":\"...\",\"ok\":true}. Use EXACTLY what it prints; never invent a verdict. On error/ok:false, record it as printed.",
    "",
    "CLAIMS:",
    numbered,
    "",
    "Return { results: [ {id, verdict, reason, ok}, ... ] } with one entry per claim id."
  ].join("\n");
}

// ---- Helpers --------------------------------------------------------------
function isDegenerate(ans) {
  if (typeof ans !== "string") return true;
  const s = ans.trim();
  if (s.length < 200) return true;
  if (/diagnostic (minimal|finding|open|answer)/i.test(s)) return true;
  return false;
}

// Inline fallback if the nested research-synthesize is unavailable.
async function miniResearch() {
  const ANGLES = [
    "authoritative primary sources and official code/repos/specs",
    "independent secondary coverage, reviews, and criticism",
    "recent developments and community discussion"
  ];
  const sweeps = await parallel(ANGLES.map((a, i) => () =>
    agent(
      "Search for the best sources on this question, focusing on: " + a + ".\n" + TOOL_NOTE +
      "\n\nQUESTION: " + question + "\nReturn up to 6 real sources with URL and the specific claim each makes.",
      {
        schema: { type: "object", additionalProperties: false, properties: { sources: { type: "array", items: { type: "object", additionalProperties: false, properties: { url: { type: "string" }, title: { type: "string" }, candidate_claim: { type: "string" } }, required: ["url"] } } }, required: ["sources"] },
        agentType: "general-purpose", phase: "Research", label: "mini-sweep:" + i
      }
    )));
  const sources_considered = [];
  for (const s of sweeps.filter(Boolean)) for (const src of (s.sources || [])) sources_considered.push({ url: src.url, title: src.title || "", read: false, candidate_claim: src.candidate_claim || "" });
  const synth = await agent(
    "Synthesize a cited answer from these gathered sources (synthesis of what sources say, not ground truth). QUESTION: " + question + "\n\nSOURCES:\n" + JSON.stringify(sources_considered, null, 2),
    {
      schema: { type: "object", additionalProperties: false, properties: { answer: { type: "string" }, key_findings: { type: "array", items: { type: "object", additionalProperties: false, properties: { finding: { type: "string" }, sources: { type: "array", items: { type: "string" } } }, required: ["finding"] } } }, required: ["answer"] },
      phase: "Research", label: "mini-synth"
    });
  return { answer: (synth && synth.answer) || "(mini-research produced no answer)", key_findings: (synth && synth.key_findings) || [], open_questions: [], confidence: "low", sources_considered, depth: "mini-fallback", rounds_run: 1 };
}

function extractPrompt(research) {
  return [
    "Extract the load-bearing factual claims from this research answer so they can be independently verified.",
    "QUESTION: " + question,
    "",
    "RESEARCH ANSWER:",
    typeof research.answer === "string" ? research.answer : JSON.stringify(research.answer),
    "",
    "KEY FINDINGS:",
    JSON.stringify(research.key_findings || [], null, 2),
    "",
    "Return " + Math.min(maxClaims, 8) + " or fewer single, checkable claims — the ones that, if false, would change the conclusion. Prefer specific/technical/named claims over vague ones."
  ].join("\n");
}

function refutePrompt(claim, research, angleIdx) {
  const angles = [
    "Find the PRIMARY source (original paper, official code repo, or first-party site) and check the claim directly. Quote the exact line/fact.",
    "Look for INDEPENDENT (second-party) corroboration or contradiction — NOT the subject's own README/marketing. If the only support is self-published, treat the claim as uncertain at best.",
    "Attack the claim's specifics (names, numbers, dates, definitions): are they exactly right, or is a plausible-but-wrong detail smuggled in?"
  ];
  return [
    "You are a skeptic. Try to REFUTE the claim below. Default to \"refuted\" or \"uncertain\" if you cannot find solid independent/primary support. Confirm ONLY if primary or independent evidence clearly backs it.",
    "QUESTION CONTEXT: " + question,
    "",
    "CLAIM TO CHECK: " + claim.claim,
    "",
    "Verification angle for THIS check: " + angles[angleIdx % angles.length],
    "",
    TOOL_NOTE,
    "",
    "Sources already gathered (you may re-fetch, but seek NEW independent/primary evidence):",
    JSON.stringify((research.sources_considered || []).map((s) => ({ url: s.url, read: s.read })), null, 2),
    "",
    "Return your verdict (confirmed / refuted / uncertain), the specific evidence, and the source URLs you actually retrieved."
  ].join("\n");
}

function reportPrompt(research, graded) {
  return [
    "Write the final, verification-aware answer. Be precise and honest: where a claim was refuted or only uncertain, say so and adjust the answer; do not repeat unverified claims as fact.",
    "QUESTION: " + question,
    "",
    "RESEARCH ANSWER (may be degenerate — rebuild from findings + sources if so):",
    typeof research.answer === "string" ? research.answer : JSON.stringify(research.answer),
    "",
    "RESEARCH KEY FINDINGS:",
    JSON.stringify(research.key_findings || [], null, 2),
    "",
    "RESEARCH SOURCES CONSIDERED:",
    JSON.stringify(research.sources_considered || [], null, 2),
    "",
    "CLAIM VERIFICATION RESULTS (verdict per load-bearing claim; each may carry an `external` verdict from an INDEPENDENT non-Opus family — where `external_dissent` is true, a different model family disputed a locally-confirmed claim, so treat it as at most UNCERTAIN and flag it):",
    JSON.stringify(graded, null, 2),
    "",
    "Produce: a calibrated answer; a graded_claims list (claim + status confirmed/refuted/uncertain + note + independent sources); remaining open_questions; and an overall confidence reflecting how much survived independent verification. Never claim measured parity."
  ].join("\n");
}

// ---- Run ------------------------------------------------------------------
phase("Research");
log("research-verify (depth=" + depth + ", voters=" + votersN + "): gathering sources, then verifying claims against primary sources.");

let research;
try {
  research = await workflow({ scriptPath: RESEARCH }, { question, depth });
  if (!research || isDegenerate(research.answer)) {
    log("Nested research answer degenerate/empty — running inline mini-research fallback.");
    const mini = await miniResearch();
    if (research && Array.isArray(research.sources_considered) && research.sources_considered.length) {
      mini.sources_considered = research.sources_considered;
      if (research.key_findings && research.key_findings.length) mini.key_findings = research.key_findings;
    }
    research = mini;
  }
} catch (e) {
  log("workflow() compose failed (" + (e && e.message) + ") — inline mini-research fallback.");
  research = await miniResearch();
}

phase("Extract");
let extracted = null;
try {
  extracted = await agent(extractPrompt(research), { schema: CLAIMS_SCHEMA, phase: "Extract", label: "extract" });
} catch (e) {
  // A schema-retry-cap failure throws; catch it so extraction failure degrades to
  // "return the research answer unverified" rather than killing the run.
  log("Claim-extraction agent errored (" + (e && e.message) + "); returning the research answer unverified.");
}
const claims = (extracted && Array.isArray(extracted.claims)) ? extracted.claims.slice(0, maxClaims) : [];

if (claims.length === 0) {
  // Nothing to verify — return the research answer honestly, unverified.
  return {
    answer: research.answer,
    graded_claims: [],
    open_questions: (research.open_questions || []).concat(["No load-bearing claims could be extracted for verification; the answer above is UNVERIFIED."]),
    confidence: "low",
    research_meta: { depth: research.depth, rounds_run: research.rounds_run, sources_count: (research.sources_considered || []).length },
    notes: HONESTY
  };
}

phase("Verify");
log("Verifying " + claims.length + " load-bearing claim(s) with " + votersN + " Opus skeptic(s) each" + (externalVerify ? " + 1 independent non-Opus cross-check" : "") + ".");

const extPromise = (externalVerify && claims.length > 0)
  ? (async () => {
      try {
        const r = await agent(extRelayPrompt(claims), { schema: EXT_RELAY_SCHEMA, phase: "Verify", label: "ext-verify:codex" });
        const map = {};
        for (const x of ((r && r.results) || [])) if (x && x.id) map[x.id] = x;
        return map;
      } catch (e) {
        log("External claim cross-check errored (" + (e && e.message) + "); Opus-only verification.");
        return {};
      }
    })()
  : Promise.resolve({});

const gradedPromise = parallel(
  claims.map((c) => () =>
    parallel(Array.from({ length: votersN }, (_v, ai) => () =>
      agent(refutePrompt(c, research, ai), { schema: VERDICT_SCHEMA, agentType: "general-purpose", phase: "Verify", label: "verify:" + c.id + ":" + ai })
    )).then((votes) => {
      const v = votes.filter(Boolean);
      const conf = v.filter((x) => x.verdict === "confirmed").length;
      const ref = v.filter((x) => x.verdict === "refuted").length;
      let status = "uncertain";
      if (ref > conf) status = "refuted";
      else if (conf > 0 && ref === 0) status = "confirmed";
      const srcs = [];
      for (const x of v) for (const s of (x.sources || [])) srcs.push(s);
      return { id: c.id, claim: c.claim, status, votes: v, sources: [...new Set(srcs)] };
    })
  )
);

const [gradedRaw, extMap] = await Promise.all([gradedPromise, extPromise]);
// Merge: downgrade-only. External refutation of a 'confirmed' -> 'uncertain'; external
// 'survives' never upgrades a tool-grounded verdict. Record dissent.
const gradedClean = gradedRaw.filter(Boolean).map((g) => {
  const ext = extMap[g.id];
  const extUsable = !!(ext && ext.ok);
  const extRefuted = extUsable && ext.verdict === "refuted";
  let status = g.status;
  let externalDissent = false;
  if (extRefuted && status === "confirmed") { status = "uncertain"; externalDissent = true; }
  return { ...g, status, external: ext ? { verdict: ext.verdict, reason: ext.reason || "", usable: extUsable, model: "codex" } : { usable: false }, external_dissent: externalDissent };
});

phase("Report");
let report = null;
try {
  report = await agent(reportPrompt(research, gradedClean), { schema: REPORT_SCHEMA, phase: "Report", label: "report" });
} catch (e) {
  log("Report-synthesis agent errored (" + (e && e.message) + "); returning raw claim verdicts.");
}

if (report) {
  return {
    answer: report.answer,
    graded_claims: report.graded_claims || [],
    open_questions: report.open_questions || [],
    confidence: report.confidence || "low",
    verification: gradedClean.map((g) => ({ claim: g.claim, status: g.status, sources: g.sources })),
    research_meta: { depth: research.depth, rounds_run: research.rounds_run, sources_count: (research.sources_considered || []).length },
    notes: HONESTY
  };
}

// Fallback: report synthesis failed — return the graded claims directly.
return {
  answer: research.answer,
  graded_claims: gradedClean.map((g) => ({ claim: g.claim, status: g.status, sources: g.sources })),
  open_questions: (research.open_questions || []).concat(["Final report synthesis did not complete; showing raw claim verdicts."]),
  confidence: "low",
  research_meta: { depth: research.depth, rounds_run: research.rounds_run, sources_count: (research.sources_considered || []).length },
  notes: HONESTY
};

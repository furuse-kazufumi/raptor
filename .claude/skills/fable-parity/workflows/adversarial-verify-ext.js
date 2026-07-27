export const meta = {
  name: "adversarial-verify-ext",
  description:
    "Heterogeneous adversarial verification: extract load-bearing claims, then check each with BOTH Opus skeptics AND an independent non-Opus model family (OpenAI Codex / gpt-5.4 via ext_verify). De-correlates the verify signal so a confident-but-wrong claim that would survive an Opus-only majority can still be caught. A claim is refuted if EITHER the external family OR the Opus majority refutes it.",
  phases: [
    { title: "Extract", detail: "pull the load-bearing claims from the answer (Opus)" },
    { title: "Verify", detail: "Opus skeptics + external non-Opus verifier per claim, in parallel" },
    { title: "Merge", detail: "union of refutations; corrected answer + per-claim provenance" },
  ],
};

const EXT_VERIFY = "C:/dev/tools/raptor/.claude/skills/fable-parity/bin/ext_verify.py";

const CLAIMS_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    claims: { type: "array", items: { type: "string" }, description: "The load-bearing factual/logical claims that, if false, sink the conclusion." },
  },
  required: ["claims"],
};

const OPUS_VERDICT_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    verdict: { type: "string", enum: ["survives", "refuted"], description: "refuted if you found a flaw OR could not verify (default-refuted)" },
    reason: { type: "string" },
  },
  required: ["verdict", "reason"],
};

const EXT_RELAY_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    results: {
      type: "array",
      description: "One entry per input claim, in the same order.",
      items: {
        type: "object",
        additionalProperties: false,
        properties: {
          claim: { type: "string" },
          verdict: { type: "string", enum: ["survives", "refuted", "unverified"] },
          reason: { type: "string" },
          ok: { type: "boolean" },
        },
        required: ["claim", "verdict", "ok"],
      },
    },
  },
  required: ["results"],
};

function extractPrompt(answer, context) {
  return [
    "From the ANSWER below, list the load-bearing factual/logical claims as separate strings — the ones that, if false, sink the conclusion. Do not include stylistic or trivially-true statements.",
    "", "CONTEXT (may be empty):", context || "(none)",
    "", "ANSWER:", answer,
  ].join("\n");
}

function opusSkepticPrompt(claim, context) {
  return [
    "You are an INDEPENDENT adversarial checker in a clean context. You did not write the claim and owe it no charity.",
    "Try hard to REFUTE the CLAIM with evidence, a counterexample, or a logical flaw. If you cannot verify it or are uncertain, treat it as REFUTED (default-refuted).",
    "", "CLAIM:", claim,
    "", "CONTEXT (may be empty):", context || "(none)",
    "", "Return verdict (survives|refuted) and a one-sentence reason.",
  ].join("\n");
}

// The external relay agent runs ext_verify.py (OpenAI Codex) once per claim via Bash
// and returns the parsed verdicts. Kept to ONE dispatch that loops the claims so the
// orchestration stays robust; the external model family is what de-correlates the check.
function extRelayPrompt(claims, context) {
  const numbered = claims.map((c, i) => `${i + 1}. ${c}`).join("\n");
  return [
    "You are a relay to an EXTERNAL non-Opus verifier. For EACH claim below, run this exact command with the Bash tool (one run per claim), substituting the claim text for <CLAIM> and the context for <CTX>:",
    "",
    "  py -3.11 \"" + EXT_VERIFY + "\" --model codex --claim \"<CLAIM>\" --context \"<CTX>\" --timeout 180",
    "",
    "Each run prints ONE JSON line like {\"model\":\"codex\",\"verdict\":\"survives\"|\"refuted\",\"reason\":\"...\",\"ok\":true}. ",
    "Collect the parsed result for every claim. Do NOT invent verdicts — use exactly what the command prints. If a run errors or prints ok:false, record verdict as printed (default 'refuted') with ok:false.",
    "Escape any embedded quotes in the claim so the shell command is valid. Preserve claim order.",
    "",
    "CONTEXT (<CTX>): " + (context ? JSON.stringify(context) : "(none)"),
    "",
    "CLAIMS:",
    numbered,
    "",
    "Return { results: [ {claim, verdict, reason, ok}, ... ] } with one entry per claim, in order.",
  ].join("\n");
}

// ------------------------------------------------------------------- run
// The Workflow tool may deliver `args` as an object, a JSON string, or a bare
// string (observed 2026-07-05). Normalize before use so field access works.
let A = args;
if (typeof A === "string") {
  const s = A.trim();
  try { A = JSON.parse(s); } catch (e) { A = { answer: s }; }
}
A = A && typeof A === "object" ? A : {};

const answer = (A.answer || A.draft) || "";
let claims = Array.isArray(A.claims) ? A.claims.slice() : null;
const context = A.context || "";
const opusVoters = Number(A.opus_voters) || 2;

phase("Extract");
if (!claims || claims.length === 0) {
  if (!answer) {
    return { error: "provide either `claims` (string[]) or `answer` (string) to verify." };
  }
  try {
    const ex = await agent(extractPrompt(answer, context), { schema: CLAIMS_SCHEMA, phase: "Extract", label: "extract-claims" });
    claims = (ex && Array.isArray(ex.claims)) ? ex.claims : [];
  } catch (e) {
    return { error: "claim extraction failed: " + ((e && e.message) || "error") };
  }
}
if (!claims.length) return { error: "no load-bearing claims found to verify." };
log(`Verifying ${claims.length} claims: ${opusVoters} Opus skeptic(s) each + 1 external non-Opus verifier (codex).`);

phase("Verify");
// External family: one relay dispatch that loops all claims through ext_verify.py.
const extPromise = (async () => {
  try {
    const r = await agent(extRelayPrompt(claims, context), { schema: EXT_RELAY_SCHEMA, phase: "Verify", label: "ext-verify:codex" });
    return (r && Array.isArray(r.results)) ? r.results : [];
  } catch (e) {
    return [];
  }
})();

// Opus skeptics: opusVoters per claim, in parallel.
const opusPromise = parallel(
  claims.flatMap((claim, ci) =>
    Array.from({ length: opusVoters }, (_v, k) => () =>
      agent(opusSkepticPrompt(claim, context), { schema: OPUS_VERDICT_SCHEMA, phase: "Verify", label: `opus-skeptic:${ci}:${k}` })
        .then((v) => ({ ci, verdict: (v && v.verdict) || "refuted", reason: (v && v.reason) || "", src: "opus" }))
        .catch(() => ({ ci, verdict: "refuted", reason: "opus skeptic errored (default-refuted)", src: "opus" }))
    )
  )
);

const [extResults, opusResultsRaw] = await Promise.all([extPromise, opusPromise]);
const opusResults = (opusResultsRaw || []).filter(Boolean);

phase("Merge");
// Aggregate per claim. A claim is REFUTED if EITHER the external family refutes it
// OR the Opus-skeptic majority refutes it (union = strongest catch).
const perClaim = claims.map((claim, ci) => {
  const opusVotes = opusResults.filter((r) => r.ci === ci);
  const opusRefuted = opusVotes.filter((r) => r.verdict === "refuted").length;
  const opusMajorityRefuted = opusVotes.length > 0 && opusRefuted * 2 > opusVotes.length;

  // match external result by claim text (relay preserves order but match defensively)
  const ext = (extResults[ci] && extResults[ci].claim === claim)
    ? extResults[ci]
    : extResults.find((e) => e && e.claim === claim) || extResults[ci] || null;
  const extRefuted = !!(ext && ext.ok && ext.verdict === "refuted");
  const extUsable = !!(ext && ext.ok);

  const finalRefuted = extRefuted || opusMajorityRefuted;
  const caughtOnlyByExternal = extRefuted && !opusMajorityRefuted;

  return {
    claim,
    verdict: finalRefuted ? "refuted" : "survives",
    caught_only_by_external: caughtOnlyByExternal,
    opus: { votes: opusVotes.length, refuted: opusRefuted, majority_refuted: opusMajorityRefuted, reasons: opusVotes.map((r) => r.reason) },
    external: ext ? { model: ext.model || "codex", verdict: ext.verdict, reason: ext.reason || "", usable: extUsable } : { usable: false, note: "no external verdict" },
  };
});

const refutedClaims = perClaim.filter((c) => c.verdict === "refuted");
const externalCatches = perClaim.filter((c) => c.caught_only_by_external);

return {
  n_claims: claims.length,
  surviving: perClaim.filter((c) => c.verdict === "survives").map((c) => c.claim),
  refuted: refutedClaims.map((c) => ({ claim: c.claim, opus_majority_refuted: c.opus.majority_refuted, external_refuted: !!c.external.usable && c.external.verdict === "refuted" })),
  external_only_catches: externalCatches.map((c) => ({ claim: c.claim, external_reason: c.external.reason })),
  per_claim: perClaim,
  guidance: refutedClaims.length
    ? "Drop or hedge every refuted claim in the answer. Claims under `external_only_catches` are exactly where the non-Opus family caught an error an Opus-only verify would have passed — the reason this workflow exists."
    : "No claim was refuted by either the Opus skeptics or the independent non-Opus family. Higher assurance than Opus-only, but not a parity guarantee.",
  caveats: "External verifier = OpenAI Codex (gpt-5.4) via ext_verify.py; a different model family from the Opus generator/skeptics, which is the de-correlation this buys. 'unverified'/unusable external results are treated as no-signal, not as pass. Never claim measured parity.",
};

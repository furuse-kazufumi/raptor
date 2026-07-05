export const meta = {
  name: "research-synthesize",
  description:
    "Multi-modal research uplift for Opus: fan out parallel search agents that each hunt a DIFFERENT angle (broad web, recent news, authoritative/primary sources, contrarian/failure cases, adjacent domains, academic, practitioner data), dedup the sources, deep-read the strongest ones for cited findings, run a completeness critic that can trigger more sweep rounds, then synthesize a cited report. Buys back Fable-tier research breadth and citation discipline by spending orchestration. It recovers thoroughness, NOT ground truth: sampling adds no facts the web does not contain, and load-bearing claims still need independent verification.",
  phases: [
    { title: "Sweep", detail: "Spawn general-purpose search agents in parallel, each locked to a distinct discovery angle so their result sets do not collapse onto the same first-page hits. Each returns candidate sources {title,url,claim} found via web tools loaded through ToolSearch." },
    { title: "Read", detail: "Dedup the pooled sources by normalized URL (multi-angle corroboration ranks a source up), then deep-read the top ones: fetch full page content and extract only findings the fetched text actually supports, each tied to its source URL. Inaccessible pages yield no fabricated findings." },
    { title: "Critic", detail: "A completeness critic inspects coverage: which modality/angle is under-sampled and which load-bearing claims are single-sourced or unverified. If gaps remain and the depth budget allows, it steers one more Sweep+Read round targeting the gaps." },
    { title: "Synthesize", detail: "One agent writes a cited report: an answer, key_findings each carrying their supporting source URLs (drawn only from the gathered set), open_questions for uncovered sub-questions and unresolved contradictions, and a confidence calibrated to breadth and corroboration — single-source claims flagged, not averaged away." }
  ]
};

// ---- Inputs ---------------------------------------------------------------
// Accept args as an object, a JSON string, or a bare string (taken as the question).
// The Workflow tool is meant to pass an object, but some callers stringify it.
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

// depth -> breadth (search angles) x read rounds. More depth = wider fan-out
// and more critic-gated rounds. readTop bounds new sources deep-read per round.
const DEPTH_CONFIG = {
  quick:    { angles: 3, rounds: 1, readTop: 4 },
  standard: { angles: 5, rounds: 2, readTop: 7 },
  deep:     { angles: 8, rounds: 3, readTop: 12 }
};
const cfg = DEPTH_CONFIG[depth];

// Fail fast on an empty question BEFORE spending any (expensive) web-search
// subagents, mirroring adversarial-verify.js's empty-input early return.
if (!hasQuestion) {
  return {
    answer: "No research question was provided; nothing to research.",
    key_findings: [],
    open_questions: ["Supply a concrete question in args.question and re-run."],
    confidence: "low",
    depth,
    rounds_run: 0,
    sources_considered: [],
    notes: "research-synthesize received no question; no subagents were spawned. This recovers research breadth, not ground truth, and claims no measured parity."
  };
}

// ---- Search angles --------------------------------------------------------
// Each agent is confined to ONE discovery angle. Diversity across angles is the
// mechanism: correlated searches re-find the same sources and add no coverage,
// so we force genuinely different modalities rather than more of the same.
const ANGLES = [
  {
    key: "broad-web",
    guidance:
      "BROAD WEB OVERVIEW. Cast the widest net for canonical, high-level, well-established sources that frame the topic: overviews, reference pages, the most-cited explainers. Goal is coverage of the mainstream consensus and vocabulary."
  },
  {
    key: "recent-news",
    guidance:
      "RECENT / TIME-SENSITIVE. Hunt the newest developments, announcements, releases, and current state. Prefer news and recently-updated pages. Surface anything that would make an older answer stale. Note publication dates where visible."
  },
  {
    key: "authoritative-primary",
    guidance:
      "AUTHORITATIVE / PRIMARY SOURCES. Go to the source of record: official documentation, standards, specifications, original announcements, first-party statements, or the primary study — not second-hand summaries of them. Prefer the closest-to-origin document you can find."
  },
  {
    key: "contrarian-failure",
    guidance:
      "CONTRARIAN / FAILURE CASES. Deliberately seek disagreement: criticism, limitations, retractions, negative results, post-mortems, 'why X is wrong / does not work', and cases where the mainstream claim failed in practice. Your job is to find what the consensus glosses over."
  },
  {
    key: "adjacent-domain",
    guidance:
      "ADJACENT DOMAIN. Look at how a DIFFERENT field or industry treats the same underlying question. Find transferable framings, analogous solutions, or cross-domain evidence that a same-field search would never surface. Name the adjacent domain explicitly."
  },
  {
    key: "academic-research",
    guidance:
      "ACADEMIC / SCHOLARLY. Target peer-reviewed papers, preprints, and formal research (e.g. arXiv, scholarly databases). Prefer sources with methodology and citations. Capture the specific finding/claim each paper makes, not just its title."
  },
  {
    key: "practitioner-empirical",
    guidance:
      "PRACTITIONER / EMPIRICAL. Find real-world reports from people who actually did the thing: case studies, benchmarks, measured data, engineering write-ups, forum threads with concrete numbers. Prefer evidence with data over opinion."
  },
  {
    key: "foundational-definitional",
    guidance:
      "FOUNDATIONAL / DEFINITIONAL. Pin down precise definitions, terminology, and the foundational background needed to interpret the other angles correctly. Surface authoritative definitions and any places the term is used ambiguously or in conflicting ways."
  }
];

// ---- Schemas --------------------------------------------------------------
const SWEEP_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    angle: { type: "string", description: "The discovery angle you were assigned." },
    sources: {
      type: "array",
      description: "Candidate sources you actually found via web tools. Do NOT invent URLs; only list pages you retrieved from a real search.",
      items: {
        type: "object",
        additionalProperties: false,
        properties: {
          title: { type: "string", description: "Page/source title." },
          url: { type: "string", description: "The real URL returned by the search tool." },
          claim: { type: "string", description: "The one specific, on-topic claim this source appears to make (why it is worth reading)." }
        },
        required: ["url", "claim"]
      }
    }
  },
  required: ["sources"]
};

const READ_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    url: { type: "string", description: "The URL you were asked to read." },
    accessible: { type: "boolean", description: "True only if you fetched real page content. False for paywalled / dead / blocked / empty pages." },
    findings: {
      type: "array",
      description: "Findings the FETCHED TEXT actually supports and that bear on the research question. Empty if the page was inaccessible or off-topic. Never fabricate.",
      items: {
        type: "object",
        additionalProperties: false,
        properties: {
          finding: { type: "string", description: "A single supported statement, in your own words." },
          evidence: { type: "string", description: "Short quote or paraphrase from the page that backs this finding." },
          relevance: { type: "string", enum: ["high", "medium", "low"], description: "How directly this bears on the question." }
        },
        required: ["finding"]
      }
    }
  },
  required: ["url", "accessible", "findings"]
};

const CRITIC_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    complete: { type: "boolean", description: "True ONLY if coverage is saturated across angles AND the load-bearing claims are corroborated by more than one independent source." },
    coverage_note: { type: "string", description: "One line: what is well-covered vs thin." },
    missing_angles: { type: "array", items: { type: "string" }, description: "Modalities/angles still under-sampled (e.g. 'no primary source', 'no contrarian evidence', 'no recent data')." },
    unverified_claims: { type: "array", items: { type: "string" }, description: "Key claims currently resting on a single source or no source." },
    suggested_queries: { type: "array", items: { type: "string" }, description: "Concrete follow-up searches that would close the biggest gaps." }
  },
  required: ["complete"]
};

const SYNTH_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    answer: { type: "string", description: "The synthesized answer to the research question, grounded in the gathered findings." },
    key_findings: {
      type: "array",
      description: "The load-bearing findings, each with the source URL(s) that support it.",
      items: {
        type: "object",
        additionalProperties: false,
        properties: {
          finding: { type: "string", description: "A supported finding." },
          sources: { type: "array", items: { type: "string" }, description: "Supporting source URL(s), drawn ONLY from the gathered set. Never invent a URL." }
        },
        required: ["finding", "sources"]
      }
    },
    open_questions: { type: "array", items: { type: "string" }, description: "Sub-questions left uncovered, contradictions unresolved, or claims still single-sourced. Do NOT hide these." },
    confidence: { type: "string", enum: ["low", "medium", "high"], description: "Confidence calibrated to breadth of sources and degree of corroboration — not to how clean the prose reads." }
  },
  required: ["answer", "key_findings", "open_questions", "confidence"]
};

// ---- Helpers --------------------------------------------------------------
function normUrl(u) {
  if (typeof u !== "string") return "";
  let s = u.trim();
  if (!s) return "";
  s = s.replace(/#.*$/, "");                                   // drop fragment
  s = s.replace(/[?&](utm_[^=&]+|ref|fbclid|gclid|mc_[^=&]+)=[^&]*/gi, ""); // drop trackers
  s = s.replace(/[?&]+$/, "");                                 // trailing ? or &
  s = s.replace(/\/+$/, "");                                   // trailing slashes
  return s.toLowerCase();
}

function hostOf(u) {
  const m = /^https?:\/\/([^/]+)/i.exec(u || "");
  return m ? m[1].replace(/^www\./i, "") : String(u || "source").slice(0, 40);
}

// url(normalized) -> { url, title, angleCount, claims[] }
const sources = new Map();
// normalized url -> read result
const readByKey = new Map();
// accumulated { finding, source, evidence, relevance }
const findings = [];

function mergeSweep(results) {
  let added = 0;
  for (const r of results) {
    if (!r || !Array.isArray(r.sources)) continue;
    for (const s of r.sources) {
      if (!s || typeof s.url !== "string") continue;
      const key = normUrl(s.url);
      if (!key) continue;
      const existing = sources.get(key);
      if (existing) {
        existing.angleCount += 1;
        if (s.claim) existing.claims.push(s.claim);
        if (!existing.title && s.title) existing.title = String(s.title).trim();
      } else {
        sources.set(key, {
          url: s.url.trim(),
          title: (s.title ? String(s.title).trim() : ""),
          angleCount: 1,
          claims: s.claim ? [String(s.claim)] : []
        });
        added += 1;
      }
    }
  }
  return added;
}

function pickToRead(n) {
  const candidates = [];
  for (const [key, v] of sources.entries()) {
    if (readByKey.has(key)) continue;
    candidates.push({ key, url: v.url, title: v.title, angleCount: v.angleCount });
  }
  // Corroboration first: a source surfaced by multiple angles is more likely load-bearing.
  candidates.sort((a, b) => (b.angleCount - a.angleCount) || (a.url < b.url ? -1 : 1));
  return candidates.slice(0, n);
}

function sourceDigest() {
  const out = [];
  for (const [key, v] of sources.entries()) {
    out.push({
      url: v.url,
      title: v.title,
      corroborations: v.angleCount,
      read: readByKey.has(key),
      candidate_claim: v.claims[0] || ""
    });
  }
  return out;
}

// ---- Prompt builders ------------------------------------------------------
const TOOL_NOTE =
  "TOOL ACCESS: web tools are NOT preloaded. You must first call ToolSearch to load one, then call it. " +
  "For search use ToolSearch query \"select:firecrawl_search\" (preferred) or \"select:WebSearch\" (fallback), or \"web search\" to discover options. " +
  "For opening a page use ToolSearch query \"select:WebFetch\" or \"select:firecrawl_scrape\". Only report URLs a real tool actually returned.";

function sweepPrompt(angle, round, critic) {
  const lines = [
    "You are ONE search agent among several running in parallel, each assigned a DIFFERENT discovery angle. You cannot see the others.",
    "Find the best real sources for the research question UNDER YOUR ASSIGNED ANGLE ONLY. Staying in your lane is the point — it is what makes the pooled result set broad.",
    "",
    "ASSIGNED ANGLE: " + angle.key,
    angle.guidance,
    "",
    TOOL_NOTE,
    "",
    "Return 3-8 sources. Each must be a page you actually retrieved, with its real URL and the one specific on-topic claim that makes it worth a deep read. If a search returns nothing usable for your angle, return an empty list rather than padding with off-angle or invented links."
  ];
  if (round > 0 && critic) {
    lines.push(
      "",
      "THIS IS A GAP-FILLING FOLLOW-UP ROUND. Earlier rounds already ran; do NOT re-find the obvious top hits. Target these identified gaps within your angle:",
      "  missing angles: " + JSON.stringify(critic.missing_angles || []),
      "  unverified claims needing a second source: " + JSON.stringify(critic.unverified_claims || []),
      "  suggested queries: " + JSON.stringify(critic.suggested_queries || [])
    );
  }
  lines.push("", "RESEARCH QUESTION:", question);
  return lines.join("\n");
}

function readPrompt(src) {
  return [
    "You are a deep-reader. Fetch the FULL content of the single source below and extract findings that bear on the research question.",
    "",
    TOOL_NOTE,
    "",
    "Discipline:",
    "- Extract ONLY findings the fetched text actually supports; attach a short supporting quote/paraphrase as evidence.",
    "- If the page is paywalled, dead, blocked, empty, or off-topic, set accessible=false and return NO findings. Do not guess the contents from the URL or title.",
    "- Do not import outside knowledge; this is about what THIS page says.",
    "",
    "SOURCE TO READ:",
    "  title: " + (src.title || "(untitled)"),
    "  url: " + src.url,
    "",
    "RESEARCH QUESTION:",
    question
  ].join("\n");
}

function criticPrompt(roundsLeft) {
  return [
    "You are a completeness critic for a research sweep. Judge COVERAGE, not just correctness.",
    "Given the research question, the pooled sources, and the extracted findings, decide whether the investigation is saturated.",
    "Mark complete=true ONLY if: multiple angles are represented (not all sources from one modality), the main sub-questions each have at least one supporting source, and the load-bearing claims are corroborated by more than one independent source.",
    "Otherwise list the specific gaps: which angle/modality is thin, which claims rest on a single source, and concrete follow-up queries that would close the biggest gaps.",
    roundsLeft > 0
      ? "There is budget for another sweep round, so gaps you name will actually be pursued — be specific and actionable."
      : "This is the final round (no more sweep budget); your gaps will become open_questions in the report, so be precise about what stayed uncovered.",
    "",
    "RESEARCH QUESTION:",
    question,
    "",
    "POOLED SOURCES:",
    JSON.stringify(sourceDigest(), null, 2),
    "",
    "EXTRACTED FINDINGS:",
    JSON.stringify(findings, null, 2)
  ].join("\n");
}

function synthPrompt(lastCritic) {
  return [
    "You are writing a cited research synthesis from the gathered sources and extracted findings. This is a synthesis of what the sources say — NOT ground truth.",
    "Method:",
    "1. Ground every key_finding in one or more of the gathered source URLs. Use ONLY URLs that appear in the source/finding data below — never invent or guess a URL.",
    "2. A claim supported by multiple INDEPENDENT sources is strong; a single-source claim is weak — flag it in open_questions rather than stating it as settled.",
    "3. Where sources CONTRADICT, surface the disagreement explicitly; do not average it into a bland middle.",
    "4. open_questions must include sub-questions no source answered and any angle the critic flagged as thin. Do not hide gaps to look thorough.",
    "5. Calibrate confidence to breadth of sources and degree of corroboration. If coverage is narrow or one-sided, say low/medium honestly. Do NOT claim certainty the evidence does not support, and do not fabricate specifics (names, numbers, citations) absent from the findings.",
    "",
    "RESEARCH QUESTION:",
    question,
    "",
    "GATHERED SOURCES (only these URLs may be cited):",
    JSON.stringify(sourceDigest(), null, 2),
    "",
    "EXTRACTED FINDINGS:",
    JSON.stringify(findings, null, 2),
    "",
    "LATEST COMPLETENESS CRITIQUE (for open_questions):",
    JSON.stringify(lastCritic || { note: "no critique available" }, null, 2)
  ].join("\n");
}

// ---- Rounds: Sweep -> Read -> Critic (critic gates continuation) ----------
log(`Research synthesis (depth=${depth}): ${cfg.angles} angles, up to ${cfg.rounds} round(s).`);

let critic = null;
let roundsRun = 0;

for (let round = 0; round < cfg.rounds; round++) {
  roundsRun = round + 1;
  const roundsLeft = cfg.rounds - 1 - round;

  // ---- Sweep (parallel, one agent per angle, general-purpose for web tools)
  phase("Sweep");
  const roundAngles = ANGLES.slice(0, cfg.angles);
  log(`Round ${roundsRun}: sweeping ${roundAngles.length} angles in parallel.`);
  const sweepResults = await parallel(
    roundAngles.map((a) => () =>
      agent(sweepPrompt(a, round, critic), {
        schema: SWEEP_SCHEMA,
        agentType: "general-purpose",
        phase: "Sweep",
        label: "sweep:" + a.key
      })
    )
  );
  const newlyAdded = mergeSweep(sweepResults.filter(Boolean));
  log(`Round ${roundsRun}: ${newlyAdded} new source(s); ${sources.size} unique total.`);

  // ---- Read (dedup already done in the map; deep-read the top unread ones)
  phase("Read");
  const toRead = pickToRead(cfg.readTop);
  if (toRead.length === 0) {
    log(`Round ${roundsRun}: no new sources to read.`);
  } else {
    log(`Round ${roundsRun}: deep-reading top ${toRead.length} source(s).`);
    const reads = await parallel(
      toRead.map((src) => () =>
        agent(readPrompt(src), {
          schema: READ_SCHEMA,
          agentType: "general-purpose",
          phase: "Read",
          label: "read:" + hostOf(src.url)
        })
      )
    );
    for (let i = 0; i < toRead.length; i++) {
      const src = toRead[i];
      const res = reads[i];
      readByKey.set(src.key, res || { url: src.url, accessible: false, findings: [] });
      if (res && res.accessible && Array.isArray(res.findings)) {
        for (const f of res.findings) {
          if (f && f.finding) {
            findings.push({
              finding: f.finding,
              source: src.url,
              evidence: f.evidence || "",
              relevance: f.relevance || "medium"
            });
          }
        }
      }
    }
  }
  log(`Round ${roundsRun}: ${findings.length} supported finding(s) accumulated.`);

  // ---- Critic (completeness; can end the loop early or steer the next round)
  phase("Critic");
  critic = await agent(criticPrompt(roundsLeft), {
    schema: CRITIC_SCHEMA,
    phase: "Critic",
    label: "critic:round" + roundsRun
  });

  if (critic && critic.complete) {
    log(`Round ${roundsRun}: critic judged coverage saturated; stopping early.`);
    break;
  }
  if (roundsLeft > 0) {
    log(`Round ${roundsRun}: gaps remain; steering another sweep round.`);
  }
}

// ---- Synthesize -----------------------------------------------------------
phase("Synthesize");
const honesty =
  "Research synthesis over web sources; this recovers breadth and citation discipline, it is not ground truth. Load-bearing claims should be verified independently. No parity with any stronger model is claimed or measured.";

let synthesis = null;
if (findings.length > 0 || sources.size > 0) {
  synthesis = await agent(synthPrompt(critic), {
    schema: SYNTH_SCHEMA,
    phase: "Synthesize",
    label: "synthesize"
  });
}

const sources_considered = sourceDigest();

if (synthesis) {
  return {
    answer: synthesis.answer,
    key_findings: Array.isArray(synthesis.key_findings) ? synthesis.key_findings : [],
    open_questions: Array.isArray(synthesis.open_questions) ? synthesis.open_questions : [],
    confidence: synthesis.confidence || "low",
    depth,
    rounds_run: roundsRun,
    sources_considered,
    notes: honesty
  };
}

// Fallback: synthesis unavailable — return the raw gathered findings honestly
// rather than fabricating an answer.
return {
  answer: sources.size === 0
    ? "No sources were retrieved for this question; unable to produce a synthesis. Re-run, broaden the question, or check web-tool availability."
    : "Synthesis step did not complete. Returning the gathered findings unmerged; treat as provisional.",
  key_findings: findings.map((f) => ({ finding: f.finding, sources: [f.source] })),
  open_questions: critic && Array.isArray(critic.missing_angles)
    ? critic.missing_angles.concat(Array.isArray(critic.unverified_claims) ? critic.unverified_claims : [])
    : ["Coverage was not assessed; treat this result as incomplete."],
  confidence: "low",
  depth,
  rounds_run: roundsRun,
  sources_considered,
  notes: honesty
};

export const meta = {
  name: 'qual-parity-capture',
  description: 'Capture 3-arm answers (opus-raw, fable-raw, opus+deep-reason+ext) on quality-discriminating open-ended tasks. No in-workflow grading — a blind independent codex judge ranks afterwards. Freezes the perishable Fable answers.',
  phases: [ { title: 'Generate' } ],
}
const DEEP_REASON = 'C:/dev/tools/raptor/.claude/skills/fable-parity/workflows/deep-reason.js'
const TASKS = [
  {
    "id": "q1",
    "archetype": "code-design",
    "prompt": "Design a multi-tenant API rate limiter that must be FAIR across tenants with wildly different traffic volumes (some 10 req/s, some 10k req/s), degrade gracefully when the shared Redis backend is unavailable, and avoid BOTH per-tenant starvation AND global thundering-herd on limit reset. Specify: the data structures, the exact algorithm for allow/deny, the fairness mechanism, the Redis-outage failure semantics, and the THREE subtlest correctness pitfalls someone implementing this would most likely get wrong (with why). Be concrete and rigorous."
  },
  {
    "id": "q2",
    "archetype": "adversarial-spec",
    "prompt": "Write a RIGOROUS, TOTAL specification for a function parse_iso8601_duration(s) that parses an ISO-8601 duration string (e.g. 'P3Y6M4DT12H30M5S', 'PT0S', 'P1W') into a normalized structure. Define the exact accepted grammar (including the week form and the fact that the time designator T is required iff any time component is present), then enumerate EVERY adversarial / edge-case input class and specify the precise behavior (accept-with-value or a defined error) for each — including: empty, missing P, T with no time parts, out-of-order components, fractional seconds vs fractional other fields, negative/signed values, overflow-scale values, mixed week-and-other, lowercase designators, and unicode digits. Argue the spec is TOTAL (every input maps to a defined outcome)."
  },
  {
    "id": "q3",
    "archetype": "hard-analysis",
    "prompt": "Compare Fibonacci heaps vs pairing heaps as the priority queue for Dijkstra's algorithm. Give the worst-case and amortized costs of the relevant operations (insert, extract-min, decrease-key) for each, derive the resulting overall Dijkstra bound on a graph with V vertices and E edges, and state precisely WHERE each heap wins (sparse vs dense E, theory vs practice). Identify the single most subtle point in the amortized (potential-function) argument for decrease-key that is most often stated incorrectly, and state it correctly."
  },
  {
    "id": "q4",
    "archetype": "debugging-reasoning",
    "prompt": "A service intermittently returns stale data: about 1 request in 10,000 reads a value that was overwritten seconds earlier. The stack is: clients -> load balancer -> N stateless app servers -> a Redis cache (read-through) -> Postgres primary with one async read-replica. Enumerate ALL plausible root causes for the stale reads, rank them by likelihood given the '1 in 10,000, seconds-stale' signature, and for the top 3 give a DEFINITIVE test that distinguishes that cause from the others (an experiment or a specific log/metric to check). Be precise about why the signature points where it does."
  },
  {
    "id": "q5",
    "archetype": "systems-tradeoff",
    "prompt": "A single hot counter (e.g. a like-count on a viral item) is receiving very high concurrent increments across many app servers. Analyze the trade-off between (a) a single-row atomic UPDATE in Postgres, (b) Redis INCR, and (c) sharded/approximate counters (N sub-counters summed on read). Derive analytically how throughput and read-accuracy scale with contention for each, state the crossover points and the assumptions behind them, and recommend a policy that is correct under a Redis outage. Show the reasoning, not just a conclusion."
  }
];
function directPrompt(t){ return ['Answer the following completely, rigorously, and concretely. This is a hard open-ended problem; depth, coverage of edge cases, and correctness of subtle points matter.', '', 'TASK:', t.prompt].join('\n') }
async function armAgent(t, model, arm){ try { const a = await agent(directPrompt(t), { model, phase:'Generate', label: arm+':'+t.id }); return { arm, model, answer:a }; } catch(e){ return { arm, model, answer:null, error:(e&&e.message)||'error' }; } }
async function deepReason(t){ try { const r = await workflow({ scriptPath: DEEP_REASON }, { task: t.prompt, attempts: 3 }); return { arm:'opus+deep-reason', model:'opus(orchestrated+ext)', answer: r && r.answer, external_summary: r && r.external_summary }; } catch(e){ return { arm:'opus+deep-reason', model:'opus(orchestrated+ext)', answer:null, error:(e&&e.message)||'error' }; } }
phase('Generate')
log('Quality parity capture: ' + TASKS.length + ' open-ended tasks x 3 arms (opus-raw, fable-raw, opus+deep-reason). Freezing Fable answers.')
const per = await parallel(TASKS.map((t) => async () => {
  const arms = await parallel([ () => armAgent(t,'opus','opus-raw'), () => armAgent(t,'fable','fable-raw'), () => deepReason(t) ])
  return { id: t.id, archetype: t.archetype, prompt: t.prompt, arms: arms.filter(Boolean) }
}))
return {
  per_task: per.filter(Boolean).map((p) => ({ id:p.id, archetype:p.archetype, prompt:p.prompt,
    arms: p.arms.map((a)=>({ arm:a.arm, model:a.model, answer:a.answer||null, error:a.error||null, external_summary:a.external_summary||null })) })),
  caveats: 'Answers only; blind independent judging happens outside the workflow (codex ranks anonymized A/B/C per task). fable-raw is the perishable arm being frozen.',
}

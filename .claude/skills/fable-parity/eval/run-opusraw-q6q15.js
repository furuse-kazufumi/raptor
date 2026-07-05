export const meta = { name:'opusraw-q6q15', description:'opus-raw single pass on q6-q15 to pair with frozen fable-raw for a cheap 2-way Opus-vs-Fable quality gap judge.', phases:[{title:'Opus'}] }
const TASKS = [
  {
    "id": "q6",
    "archetype": "code-design",
    "prompt": "Design an idempotent webhook DELIVERY system (you are the sender): at-least-once delivery, exactly-once EFFECT on the receiver, retry with exponential backoff + jitter, and poison-message handling. Specify the dedup key and where it lives, the storage schema, ordering guarantees (and when ordering must be sacrificed), the retry state machine, and the THREE subtlest correctness pitfalls (e.g. dedup-window expiry vs late retries) with why each bites."
  },
  {
    "id": "q7",
    "archetype": "adversarial-spec",
    "prompt": "Write a RIGOROUS TOTAL specification for compare(a, b) comparing two Semantic Versioning 2.0.0 strings, returning -1/0/1. Define the exact grammar, then specify precedence for: major/minor/patch numerically; pre-release vs release (pre-release is LOWER); dotted pre-release identifier comparison (numeric identifiers compared numerically, alphanumeric lexically, numeric < alphanumeric, a larger set of fields wins when all preceding equal); and that BUILD METADATA is ignored for precedence. Enumerate adversarial inputs (leading zeros in numeric identifiers, empty identifiers, huge numbers, unicode, missing patch, 'v' prefix) and define accept/error for each. Argue totality."
  },
  {
    "id": "q8",
    "archetype": "hard-analysis",
    "prompt": "Compare consistent hashing (ring + virtual nodes) vs rendezvous / highest-random-weight (HRW) hashing for a distributed cache. For each: the fraction of keys remapped when a node is added or removed, the load-balance variance (and how virtual nodes / HRW affect it), and the per-lookup cost. State precisely where each wins, and identify the single most common misconception about consistent hashing's remapping guarantee and correct it."
  },
  {
    "id": "q9",
    "archetype": "debugging-reasoning",
    "prompt": "A web service's p99 latency spikes to 10x baseline, but ONLY at moderate load (not idle, not peak) and in bursts lasting ~200ms. p50 is unaffected. Enumerate every plausible root cause (stop-the-world GC, connection-pool exhaustion, lock/mutex contention, noisy-neighbor CPU steal, TCP retransmit/Nagle, thread-pool queueing, periodic cache stampede). Rank by fit to the EXACT signature (p99-only, moderate-load-only, ~200ms bursts, p50 fine) and for the top 3 give a definitive distinguishing test (a specific metric, trace, or experiment)."
  },
  {
    "id": "q10",
    "archetype": "systems-tradeoff",
    "prompt": "For an order-management system that needs full history, temporal ('as-of') queries, and audit compliance, analyze event sourcing vs CRUD-with-an-audit-log. Derive the trade-offs on: query complexity for current-state vs historical, storage growth, consistency/rebuild risk, schema-evolution pain, and operational complexity. State the crossover conditions (when each is the right call) and give a concrete recommendation with its assumptions."
  },
  {
    "id": "q11",
    "archetype": "proof-reasoning",
    "prompt": "Prove the correctness of the sort-then-two-pointer algorithm for 3SUM (find all unique triples summing to 0). State the loop invariant for the inner two-pointer scan, prove it never MISSES a valid pair for the fixed first element, prove it enumerates each triple at most once (the deduplication argument), and state the exact complexity with justification. Be rigorous about why moving the pointers is safe."
  },
  {
    "id": "q12",
    "archetype": "concurrency",
    "prompt": "Design a bounded blocking queue (fixed capacity) for multiple producers and multiple consumers using ONLY a mutex and condition variable(s). Specify the exact lock/wait/signal discipline (which predicate each wait re-checks, why it MUST be a while-loop not an if, when to signal vs broadcast). Explain the two classic bugs — lost wakeup and the thundering-herd / spurious-wakeup problem — and show precisely how your discipline prevents each. State whether one condvar or two is correct and why."
  },
  {
    "id": "q13",
    "archetype": "distributed",
    "prompt": "Explain precisely why two-phase commit (2PC) BLOCKS on coordinator failure: give the exact scenario (which participant states, what they cannot decide, and why) where a participant is stuck indefinitely. Then explain how three-phase commit (3PC) removes the blocking under a synchronous model, the extra cost it pays, and the failure model (network partition / asynchrony) under which 3PC still fails — and how a consensus-based commit (Paxos/Raft-backed) addresses it. Be precise about the assumptions each protocol needs."
  },
  {
    "id": "q14",
    "archetype": "data-structure",
    "prompt": "Design a data structure supporting insert(x), remove(x), and getRandom() each in O(1) average time, with getRandom uniform over current elements. Specify the two backing structures (dynamic array + hash map of value->index), the exact remove algorithm (swap-with-last then pop, and fixing the moved element's index), and the SUBTLE bug when the element being removed IS the last element (or the only element). Handle duplicates: state what changes if duplicate values must be supported."
  },
  {
    "id": "q15",
    "archetype": "numeric",
    "prompt": "Explain Kahan (compensated) summation. First show exactly why naive left-to-right floating-point summation loses precision (the mechanism: adding a small number to a large running sum drops low-order bits at rounding). Then show what Kahan's running compensation term recovers and how (walk the algorithm's update). Finally state its LIMITS precisely: what error bound Kahan achieves vs naive (O(1) vs O(n) growth in units of epsilon), and what it does NOT fix (e.g. catastrophic cancellation from subtracting nearly-equal numbers, or ill-conditioned sums)."
  }
];
function p(t){ return ['Answer completely, rigorously, concretely. Depth, edge-case coverage, and correctness of subtle points matter.','','TASK:',t.prompt].join('\n') }
phase('Opus')
const per = await parallel(TASKS.map((t)=>async()=>{ let a=null,e=null; try{ a=await agent(p(t),{model:'opus',phase:'Opus',label:'opus-raw:'+t.id}); }catch(x){ e=(x&&x.message)||'err'; } return { id:t.id, archetype:t.archetype, prompt:t.prompt, arms:[{arm:'opus-raw',model:'opus',answer:a,error:e}] }; }))
return { per_task: per.filter(Boolean) }

export const meta = {
  name: 'fable-parity-eval',
  description: 'Measure, against objective ground-truth keys, whether Opus+deep-reason closes the Opus->Fable gap on 4 hard probe tasks (3 arms: opus-raw, fable-raw, opus+deep-reason)',
  phases: [
    { title: 'Solve', detail: 'run 3 arms per task: single Opus pass, single Fable pass, and the deep-reason workflow' },
    { title: 'Grade', detail: 'objectively grade each answer against the known-correct key' },
  ],
}

const DEEP_REASON = 'C:/dev/tools/raptor/.claude/skills/fable-parity/workflows/deep-reason.js'

// 4 objectively-gradable probe tasks (deterministic ground truth from the rubrics).
const TASKS = [
  {
    id: 'p01',
    prompt: "On an island every inhabitant is either a knight (who always tells the truth) or a knave (who always lies). Four inhabitants A, B, C, D make these statements. A: 'Exactly one of the four of us is a knight.' B: 'Exactly two of the four of us are knights.' C: 'A is a knave.' D: 'B is a knave.' Determine, with full justification, which of A, B, C, D are knights and which are knaves, and state whether the solution is unique.",
    key: "A = knave, B = knight, C = knight, D = knave (exactly two knights). The solution is UNIQUE. A correct answer must give this exact assignment AND establish uniqueness (rule out other knight-counts), not just assert one consistent labeling.",
  },
  {
    id: 'p02',
    prompt: "Schedule five workshops - Design, Security, Testing, Deployment, and Compliance - into five consecutive time slots numbered 1 to 5, exactly one workshop per slot. Constraints: (1) Design must be earlier than Testing, and Testing earlier than Deployment. (2) Security must be in the slot immediately after Design. (3) Security may not be in the first or the last slot. (4) Compliance must be in some slot before Design. Produce a valid ordering, prove it satisfies all four constraints, and prove whether it is the only valid ordering.",
    key: "Unique ordering: slot 1 Compliance, slot 2 Design, slot 3 Security, slot 4 Testing, slot 5 Deployment. A correct answer must give this exact ordering AND prove uniqueness (rule out other orderings, esp. the Design-in-slot-3 near-miss), not just present one valid schedule.",
  },
  {
    id: 'p04',
    prompt: "The following Python function is intended to return the maximum sum of any contiguous subarray of length k (assume 1 <= k <= len(nums)):\n\ndef max_window_sum(nums, k):\n    best = 0\n    window = sum(nums[:k])\n    for i in range(k, len(nums)):\n        window += nums[i] - nums[i - k]\n        if window > best:\n            best = window\n    return best\n\nIt passes some tests but is wrong. Identify every bug, give a concrete input on which it returns the wrong answer (state expected vs actual), explain the root cause, and provide a corrected version.",
    key: "There are TWO distinct bugs: (1) the first window sum(nums[:k]) is never compared to best because the loop starts at index k -> the initial window can never be selected (e.g. nums=[5,1,1], k=2 returns 2 but correct is 6); (2) best is initialized to 0, which breaks all-negative inputs (e.g. nums=[-2,-1,-3], k=2 returns 0 but correct is -3). Fix: initialize best=window before the loop (or best=float('-inf') and score the first window). A correct answer must find BOTH bugs, not just one.",
  },
  {
    id: 'p08',
    prompt: "A deterministic finite state machine has three states S0, S1, S2 and starts in S0. On each input symbol it transitions as follows. On 'a': S0->S1, S1->S2, S2->S0. On 'b': S0->S0, S1->S0, S2->S1. Process this 16-symbol input one symbol at a time, left to right: a b a a b b a b a a b b a a b a. Report (1) the final state after all 16 symbols, and (2) the number of transitions (out of 16) that ended in state S2. Show the state after each symbol.",
    key: "Final state = S2. Number of transitions ending in S2 = 4 (at symbols 4, 10, 14, 16). Correct per-symbol trace of the resulting states: S1, S0, S1, S2, S1, S0, S1, S0, S1, S2, S1, S0, S1, S2, S1, S2. A correct answer must report final=S2 AND count=4 (a verifiable trace strongly preferred).",
  },
]

const GRADE_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    correct: { type: 'boolean', description: 'true ONLY if the answer states the key\'s correct result AND meets the key\'s justification bar (uniqueness proven / both bugs found / final+count both right)' },
    missed: { type: 'array', items: { type: 'string' }, description: 'what the answer got wrong or omitted vs the key' },
    note: { type: 'string' },
  },
  required: ['correct', 'missed'],
}

function directPrompt(task) {
  return [
    'Solve the following task completely. Give your full reasoning and a clear, explicit final answer.',
    '',
    'TASK:',
    task.prompt,
  ].join('\n')
}

function gradePrompt(task, armName, answer) {
  return [
    'You are objectively grading an answer against a KNOWN-CORRECT KEY. This is a correctness check against ground truth, not a style/preference judgment. Be strict but fair: mark correct=true ONLY if the answer reaches the key\'s result AND meets its justification bar.',
    '',
    'TASK:',
    task.prompt,
    '',
    'GROUND-TRUTH KEY:',
    task.key,
    '',
    'ANSWER TO GRADE (from arm "' + armName + '"):',
    typeof answer === 'string' ? answer : JSON.stringify(answer),
    '',
    'Return correct (bool), missed (list of specific errors/omissions vs the key), and a one-line note.',
  ].join('\n')
}

async function runArmAgent(task, model, armName) {
  try {
    const a = await agent(directPrompt(task), { model, phase: 'Solve', label: armName + ':' + task.id })
    return { arm: armName, model, answer: a };
  } catch (e) {
    return { arm: armName, model, answer: null, error: (e && e.message) || 'error' };
  }
}

async function runDeepReason(task) {
  try {
    const r = await workflow({ scriptPath: DEEP_REASON }, { task: task.prompt, attempts: 3 });
    return { arm: 'opus+deep-reason', model: 'opus(orchestrated)', answer: r && r.answer, meta: r && { confidence: r.confidence } };
  } catch (e) {
    return { arm: 'opus+deep-reason', model: 'opus(orchestrated)', answer: null, error: (e && e.message) || 'error' };
  }
}

phase('Solve')
log('Parity eval: 4 objective probe tasks x 3 arms (opus-raw, fable-raw, opus+deep-reason). Small-N/single-run — indicative, not a powered benchmark.')

const perTask = await pipeline(
  TASKS,
  // Stage 1: 3 arms in parallel
  async (task) => {
    const arms = await parallel([
      () => runArmAgent(task, 'opus', 'opus-raw'),
      () => runArmAgent(task, 'fable', 'fable-raw'),
      () => runDeepReason(task),
    ])
    return { task, arms: arms.filter(Boolean) }
  },
  // Stage 2: grade each arm objectively against the key
  async (prev) => {
    const { task, arms } = prev
    phase('Grade')
    const graded = await parallel(arms.map((a) => () => {
      if (!a.answer) return Promise.resolve({ ...a, grade: { correct: false, missed: ['no answer produced (arm unavailable/errored)'], note: a.error || 'no answer' } })
      return agent(gradePrompt(task, a.arm, a.answer), { schema: GRADE_SCHEMA, model: 'opus', phase: 'Grade', label: 'grade:' + task.id + ':' + a.arm })
        .then((g) => ({ ...a, grade: g || { correct: false, missed: ['grader failed'], note: 'grader returned nothing' } }))
        .catch((e) => ({ ...a, grade: { correct: false, missed: ['grader errored'], note: (e && e.message) || 'grader error' } }))
    }))
    return { id: task.id, graded: graded.filter(Boolean) }
  },
)

// Aggregate
const clean = perTask.filter(Boolean)
const arms = ['opus-raw', 'fable-raw', 'opus+deep-reason']
const tally = {}
for (const armName of arms) tally[armName] = { correct: 0, total: 0, available: 0 }
for (const t of clean) {
  for (const g of (t.graded || [])) {
    const k = g.arm
    if (!tally[k]) tally[k] = { correct: 0, total: 0, available: 0 }
    tally[k].total += 1
    if (g.answer) tally[k].available += 1
    if (g.grade && g.grade.correct) tally[k].correct += 1
  }
}

return {
  n_tasks: clean.length,
  tally,
  per_task: clean.map((t) => ({
    id: t.id,
    results: (t.graded || []).map((g) => ({ arm: g.arm, model: g.model, correct: !!(g.grade && g.grade.correct), missed: (g.grade && g.grade.missed) || [], available: !!g.answer })),
  })),
  caveats: 'N=4 objective tasks, single run per arm (no repeats) -> indicative only, not statistically powered. Grader is a single Opus judge against an explicit key (objective correctness check, low bias, but not infallible). fable-raw depends on the harness actually provisioning a Fable subagent; if it routed to Opus the upper reference is not distinct (check the model field).',
}

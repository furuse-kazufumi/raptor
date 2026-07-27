export const meta = {
  name: 'fable-parity-baseline-capture',
  description: 'Perishable Fable baseline capture: run hard probe tasks across 3 arms (opus-raw, fable-raw, opus+deep-reason), grade each against a computed key, and RETURN full answers so the Fable transcripts can be frozen before Fable access ends.',
  phases: [
    { title: 'Solve', detail: 'per task: single Opus pass, single Fable pass, and the deep-reason workflow' },
    { title: 'Grade', detail: 'objectively grade each arm against the computed ground-truth key' },
  ],
}

const DEEP_REASON = 'C:/dev/tools/raptor/.claude/skills/fable-parity/workflows/deep-reason.js'

const TASKS = [
  {
    "id": "h01",
    "category": "long-horizon",
    "prompt": "A deterministic finite state machine has four states S0,S1,S2,S3 and starts in S0. Transitions: on 'a': S0->S1,S1->S2,S2->S3,S3->S0. on 'b': S0->S2,S1->S3,S2->S0,S3->S1. on 'c': every state -> S0. Process this 30-symbol input left to right, one symbol at a time:\na a b c b a a c b b a c a a b c b a a c b b a c a a b c b a\nReport (1) the final state after all 30 symbols, and (2) how many of the 30 transitions ended in state S3. Show the state after each symbol.",
    "key": "Final state = S3. Number of transitions ending in S3 = 3. Full resulting-state trace (after each symbol): S1,S2,S0,S0,S2,S3,S0,S0,S2,S0,S1,S0,S1,S2,S0,S0,S2,S3,S0,S0,S2,S0,S1,S0,S1,S2,S0,S0,S2,S3. A correct answer must report both the final state and the S3 count exactly; a verifiable per-symbol trace is strongly preferred."
  },
  {
    "id": "h03",
    "category": "deductive-reasoning",
    "prompt": "Compute the last three digits of 3^777 (that is, 3^777 mod 1000). Show a correct method (e.g. via mod 8 and mod 125 with CRT, or repeated squaring) and the exact three-digit result.",
    "key": "3^777 mod 1000 = 763 (last three digits '763'). A correct answer must give exactly this value with a valid method."
  },
  {
    "id": "h04",
    "category": "long-horizon",
    "prompt": "How many binary strings of length 24 contain no run of three or more consecutive 1s (i.e. '111' never appears as a substring)? Give the exact integer and explain the recurrence you use.",
    "key": "Exact count = 2555757. (Satisfies a tribonacci-like recurrence a(n)=a(n-1)+a(n-2)+a(n-3).) A correct answer must give exactly this integer."
  },
  {
    "id": "h05",
    "category": "multi-constraint-planning",
    "prompt": "Place six tasks A, B, C, D, E, F into six consecutive slots numbered 1..6 (one task per slot). Constraints: (1) A is before C, and C is before E. (2) B is in the slot immediately after A. (3) D is after E. (4) F is before A. (5) B is neither first nor last. Give a valid ordering, verify all five constraints, and prove whether it is the ONLY valid ordering.",
    "key": "Unique ordering (slot1..slot6): F, A, B, C, E, D. A correct answer must give this exact ordering AND prove uniqueness (rule out alternatives), not just present one valid schedule."
  },
  {
    "id": "h06",
    "category": "estimation",
    "prompt": "Two fair six-sided dice are rolled repeatedly and their sum is taken each roll. What is the exact probability (as a reduced fraction) that a sum of 7 appears before a sum of 5? Show the reasoning.",
    "key": "Exact probability = 3/5. (P(7 before 5) = P(7)/(P(7)+P(5)) = (6/36)/((6+4)/36) = 6/10 = 3/5.) A correct answer must give exactly this reduced fraction."
  },
  {
    "id": "h07",
    "category": "deductive-reasoning",
    "prompt": "A subtraction game: a single pile starts with 40 stones. Players alternate; on a turn a player removes exactly 1, 3, or 4 stones. The player who takes the last stone WINS (normal play). With optimal play from 40 stones, does the first player (the one to move first) win or lose? Justify via the losing (P-)positions.",
    "key": "With optimal play, FIRST player WINS from 40 stones. (P-positions / losing-for-mover positions follow a period-7 pattern; 40 is a N-position (winning) for the mover.) A correct first move is to leave [37] stones. A correct answer must state the right winner with valid P-position reasoning."
  },
  {
    "id": "h08",
    "category": "long-horizon",
    "prompt": "Define a sequence by a(0)=2, a(1)=3, and a(n)=3*a(n-1) - a(n-2) + 1 for n>=2. Compute a(20) exactly. Show enough intermediate terms that the result is checkable.",
    "key": "a(20) = 292072112. (Full terms a(0..20): [2, 3, 8, 22, 59, 156, 410, 1075, 2816, 7374, 19307, 50548, 132338, 346467, 907064, 2374726, 6217115, 16276620, 42612746, 111561619, 292072112].) A correct answer must give exactly a(20)=292072112."
  },
  {
    "id": "h09",
    "category": "deductive-reasoning",
    "prompt": "Four houses stand in a row, numbered 1 to 4 left to right. Each has a distinct color (red, green, blue, yellow) and a distinct pet (cat, dog, bird, fish). Clues: (1) the green house is immediately to the right of the red house; (2) the blue house is house 1; (3) the cat lives in the yellow house; (4) the dog is in the house immediately to the left of the green house; (5) the fish is in house 4. Determine the full arrangement and state which pet lives in the GREEN house. Prove the arrangement is unique.",
    "key": "Unique arrangement -> house 1: blue, bird; house 2: yellow, cat; house 3: red, dog; house 4: green, fish. Pet in the GREEN house = fish. A correct answer must give this arrangement (or at least the correct green-house pet) with uniqueness."
  },
  {
    "id": "h10",
    "category": "debugging",
    "prompt": "This Python function is meant to return the list of prime numbers strictly less than n, in increasing order, using a sieve. It is buggy.\n\ndef primes_below(n):\n    sieve = [True] * n\n    sieve[0] = False\n    for i in range(2, int(n ** 0.5)):\n        if sieve[i]:\n            for j in range(i * i, n, i):\n                sieve[j] = False\n    return [i for i in range(n) if sieve[i]]\n\nIdentify EVERY bug, give a concrete input where the output is wrong (state expected vs actual), explain each root cause, and provide a corrected version.",
    "key": "There are THREE distinct bugs: (1) sieve[1] is never set to False, so 1 is wrongly reported as prime (e.g. primes_below(5) returns [1,2,3] but should be [2,3]). (2) The outer loop 'range(2, int(n**0.5))' stops one short: it must be 'int(n**0.5)+1'. For n where the largest needed factor equals int(sqrt(n)) it misses marking composites (e.g. n=26: sqrt~5.09, range(2,5) skips i=5, so 25 is left marked prime; primes_below(26) wrongly includes 25). (3) n=0 or n=1 crashes / misbehaves: 'sieve=[True]*n' with n=0 is empty and 'sieve[0]=False' raises IndexError (n=0), and for n=1 it also indexes sieve[0] out of an intended-empty result. A correct fix sets sieve[0]=sieve[1]=False (guarding n<2), uses range(2, int(n**0.5)+1), and handles n<=2 by returning []. A correct answer must find ALL THREE (the 1-is-prime bug, the sqrt off-by-one, and the small-n/n<=1 boundary), not a subset."
  }
];

const GRADE_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    correct: { type: 'boolean', description: 'true ONLY if the answer reaches the key result AND meets its justification bar' },
    missed: { type: 'array', items: { type: 'string' }, description: 'what the answer got wrong or omitted vs the key' },
    note: { type: 'string' },
  },
  required: ['correct', 'missed'],
}

function directPrompt(task) {
  return ['Solve the following task completely. Give your full reasoning and a clear, explicit final answer.', '', 'TASK:', task.prompt].join('\n')
}

function gradePrompt(task, armName, answer) {
  return [
    'You are objectively grading an answer against a KNOWN-CORRECT KEY. This is a correctness check against ground truth, not a style/preference judgment. Mark correct=true ONLY if the answer reaches the key result AND meets its justification bar.',
    '', 'TASK:', task.prompt,
    '', 'GROUND-TRUTH KEY:', task.key,
    '', 'ANSWER TO GRADE (from arm "' + armName + '"):',
    typeof answer === 'string' ? answer : JSON.stringify(answer),
    '', 'Return correct (bool), missed (list of specific errors/omissions vs the key), and a one-line note.',
  ].join('\n')
}

async function runArmAgent(task, model, armName) {
  try {
    const a = await agent(directPrompt(task), { model, phase: 'Solve', label: armName + ':' + task.id })
    return { arm: armName, model, answer: a }
  } catch (e) {
    return { arm: armName, model, answer: null, error: (e && e.message) || 'error' }
  }
}

async function runDeepReason(task) {
  try {
    const r = await workflow({ scriptPath: DEEP_REASON }, { task: task.prompt, attempts: 3 })
    return { arm: 'opus+deep-reason', model: 'opus(orchestrated)', answer: r && r.answer, confidence: r && r.confidence }
  } catch (e) {
    return { arm: 'opus+deep-reason', model: 'opus(orchestrated)', answer: null, error: (e && e.message) || 'error' }
  }
}

phase('Solve')
log('Baseline capture: ' + TASKS.length + ' hard tasks x 3 arms (opus-raw, fable-raw, opus+deep-reason). Freezing Fable transcripts.')

const perTask = await pipeline(
  TASKS,
  async (task) => {
    const arms = await parallel([
      () => runArmAgent(task, 'opus', 'opus-raw'),
      () => runArmAgent(task, 'fable', 'fable-raw'),
      () => runDeepReason(task),
    ])
    return { task, arms: arms.filter(Boolean) }
  },
  async (prev) => {
    const { task, arms } = prev
    phase('Grade')
    const graded = await parallel(arms.map((a) => () => {
      if (!a.answer) return Promise.resolve({ ...a, grade: { correct: false, missed: ['no answer produced'], note: a.error || 'no answer' } })
      return agent(gradePrompt(task, a.arm, a.answer), { schema: GRADE_SCHEMA, model: 'opus', phase: 'Grade', label: 'grade:' + task.id + ':' + a.arm })
        .then((g) => ({ ...a, grade: g || { correct: false, missed: ['grader failed'], note: 'grader returned nothing' } }))
        .catch((e) => ({ ...a, grade: { correct: false, missed: ['grader errored'], note: (e && e.message) || 'grader error' } }))
    }))
    return { id: task.id, category: task.category, key: task.key, graded: graded.filter(Boolean) }
  },
)

const clean = perTask.filter(Boolean)
const armNames = ['opus-raw', 'fable-raw', 'opus+deep-reason']
const tally = {}
for (const n of armNames) tally[n] = { correct: 0, total: 0, available: 0 }
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
  tally,
  per_task: clean.map((t) => ({
    id: t.id,
    category: t.category,
    key: t.key,
    arms: (t.graded || []).map((g) => ({
      arm: g.arm,
      model: g.model,
      available: !!g.answer,
      correct: !!(g.grade && g.grade.correct),
      missed: (g.grade && g.grade.missed) || [],
      confidence: g.confidence,
      answer: g.answer || null,
    })),
  })),
  caveats: 'Single run per arm, no repeats -> indicative. Grader is a single Opus judge vs an explicit computed key. fable-raw depends on the harness provisioning a real Fable subagent (check the model field). Full answers included for freezing the Fable baseline.',
}

export const meta = {
  name: 'stageA-opusraw',
  description: 'Stage A: single-pass opus-raw on the harder task set, graded vs computed keys, to find which tasks actually break opus-raw (the discriminating subset for Stage B).',
  phases: [ { title: 'Solve' }, { title: 'Grade' } ],
}
const TASKS = [
  {
    "id": "h1",
    "category": "long-horizon",
    "prompt": "A DFA has 5 states S0..S4, start S0. On 'a': Si->S(i+1 mod 5). On 'b': Si->S(i+2 mod 5). On 'c': any->S0. Process these 60 symbols left to right one at a time:\na a b c b a a b c b a a b c b a a b c b b a c a b b a c a b b a c a b b a c a b c a b b a c a b b a c a b b a c a b b a\nReport (1) the final state and (2) how many of the 60 transitions ended in S4. Show the state after each symbol.",
    "key": "Final=S1; count of transitions ending in S4 = 5. Must give BOTH exactly."
  },
  {
    "id": "h2",
    "category": "debugging",
    "prompt": "This Python function should return the number of vowels (a,e,i,o,u, case-insensitive) in a string, but it is buggy:\n\ndef count_vowels(s):\n    vowels = 'aeiou'\n    count = 0\n    for i in range(1, len(s)):\n        if s[i] in vowels:\n            count = 1\n    return count\n\nIdentify EVERY bug, give a concrete failing input (expected vs actual) for each where possible, and provide a corrected version.",
    "key": "Bugs (at least these FOUR distinct defects; a strong answer finds all): (1) range(1, len(s)) skips index 0, so a leading vowel is never counted (e.g. 'apple' -> misses the 'a'). (2) count = 1 ASSIGNS instead of increments (count += 1); it caps the result at 1 and also mis-sets to 1, so 'aeiou' returns 1 not 5. (3) case-insensitivity is claimed but not implemented: uppercase vowels are missed because vowels='aeiou' and s is not lowered (e.g. 'Apple' misses 'A'); fix by lowering s or including 'AEIOU'. (4) combined effect: correct output for 'aeiou' is 5 and for 'Apple' is 2, but the function returns 1 and 0-or-1. A correct fix: loop range(len(s)) (or 'for ch in s'), count += 1, and lowercase the char/string. A correct answer must catch the off-by-one start, the =1-vs-+=1, AND the case-sensitivity bug."
  },
  {
    "id": "h3",
    "category": "deductive-reasoning",
    "prompt": "How many integers k with 1 <= k < 1000 are divisible by at least one of 2, 3, 5, or 7? Use inclusion-exclusion over all four primes and give the exact integer.",
    "key": "Exact count = 771. Must apply full 4-set inclusion-exclusion (all 15 terms) and give exactly this integer."
  },
  {
    "id": "h6",
    "category": "long-horizon",
    "prompt": "Define a(0)=3, a(1)=5, and for n>=2: a(n) = (a(n-1)*a(n-2) + a(n-1) + 7) mod 100000. Compute a(50) exactly. Show enough intermediate terms to be checkable.",
    "key": "a(50) = 10619. Must give exactly this value."
  },
  {
    "id": "h8",
    "category": "deductive-reasoning",
    "prompt": "Wythoff-style game on two piles (13 and 20 tokens). A move is: remove any positive number of tokens from ONE pile, OR remove the SAME positive number from BOTH piles. The player who takes the last token (reaching (0,0)) wins. With optimal play from (13,20), does the player to move WIN or LOSE? Justify.",
    "key": "From (13,20) the player to move WINS. (Wythoff losing positions are (floor(n*phi), floor(n*phi^2)); check whether (13,20) is one.) Must state the correct winner with valid reasoning."
  },
  {
    "id": "h9",
    "category": "long-horizon",
    "prompt": "How many binary strings of length 30 do NOT contain '101' as a (contiguous) substring? Give the exact integer and state the recurrence.",
    "key": "Exact count = 26931732. Must give exactly this integer."
  },
  {
    "id": "h10",
    "category": "deductive-reasoning",
    "prompt": "Find the smallest positive integer x satisfying x ≡ 2 (mod 7), x ≡ 3 (mod 11), and x ≡ 5 (mod 13). Solve via CRT and give the exact value (and the modulus of the full solution set).",
    "key": "Smallest x = 135; full solution set is x ≡ 135 (mod 1001). Must give exactly this smallest value."
  },
  {
    "id": "h11",
    "category": "deductive-reasoning",
    "prompt": "On an integer grid, count monotone lattice paths from (0,0) to (6,4) using only unit steps right (+1,0) or up (0,+1), that DO NOT pass through the point (3,2). Give the exact count with reasoning.",
    "key": "Exact = C(10,4) - C(5,2)*C(5,2) = 210 - 100 = 110. Must give exactly 110."
  },
  {
    "id": "h12",
    "category": "estimation",
    "prompt": "An urn has 5 red and 3 blue balls. You draw 3 balls without replacement. What is the exact probability (reduced fraction) that exactly 2 of the 3 drawn are red? Show the counting.",
    "key": "Exact probability = 15/28 (= C(5,2)*C(3,1)/C(8,3) = 30/56 = 15/28). Must give this reduced fraction."
  }
];
const GRADE_SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    correct: { type: 'boolean', description: 'true ONLY if the answer reaches the key result AND meets its justification bar' },
    missed: { type: 'array', items: { type: 'string' } },
    note: { type: 'string' },
  },
  required: ['correct', 'missed'],
}
function directPrompt(t) {
  return ['Solve the following task completely. Give full reasoning and a clear, explicit final answer.', '', 'TASK:', t.prompt].join('\n')
}
function gradePrompt(t, answer) {
  return [
    'You are objectively grading an answer against a KNOWN-CORRECT KEY. Correctness check vs ground truth, not style. correct=true ONLY if the answer reaches the key result AND meets its justification bar.',
    '', 'TASK:', t.prompt, '', 'GROUND-TRUTH KEY:', t.key, '',
    'ANSWER TO GRADE:', typeof answer === 'string' ? answer : JSON.stringify(answer), '',
    'Return correct (bool), missed (specific errors/omissions vs the key), and a one-line note.',
  ].join('\n')
}
phase('Solve')
log('Stage A: opus-raw single pass on ' + TASKS.length + ' harder tasks.')
const per = await pipeline(
  TASKS,
  async (t) => {
    let answer = null, err = null;
    try { answer = await agent(directPrompt(t), { model: 'opus', phase: 'Solve', label: 'opus-raw:' + t.id }); }
    catch (e) { err = (e && e.message) || 'error'; }
    return { t, answer, err };
  },
  async (prev) => {
    const { t, answer, err } = prev;
    phase('Grade')
    if (!answer) return { id: t.id, category: t.category, correct: false, missed: ['no answer: ' + err], answer: null };
    let g;
    try { g = await agent(gradePrompt(t, answer), { schema: GRADE_SCHEMA, model: 'opus', phase: 'Grade', label: 'grade:' + t.id }); }
    catch (e) { g = { correct: false, missed: ['grader errored: ' + ((e && e.message) || 'err')] }; }
    return { id: t.id, category: t.category, correct: !!(g && g.correct), missed: (g && g.missed) || [], answer };
  }
)
const clean = per.filter(Boolean)
const failed = clean.filter((x) => !x.correct).map((x) => x.id)
return {
  tally: { correct: clean.filter((x) => x.correct).length, total: clean.length },
  opus_raw_failed: failed,
  per_task: clean.map((x) => ({ id: x.id, category: x.category, correct: x.correct, missed: x.missed })),
  full_answers: clean.map((x) => ({ id: x.id, answer: x.answer })),
  caveats: 'Single opus-raw pass per task, single Opus grader vs computed key. opus_raw_failed = the discriminating subset worth running Stage B (fable-raw + opus+deep-reason) on.',
}

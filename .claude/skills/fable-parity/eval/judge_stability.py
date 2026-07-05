#!/usr/bin/env python3
"""Judge self-consistency: re-run the blind codex judge K times per task with K
DIFFERENT orderings and check whether the winner is stable. Directly addresses the
'single blind judge' caveat — codex is repeatable (non-perishable), so this is cheap
and tells us if the N=5 win pattern is robust or noise.

Usage: judge_stability.py <capture-3arm.json> <date> [K=3]
"""
import json, os, subprocess, sys

EVAL = "D:/tools/raptor/.claude/skills/fable-parity/eval"
EXT_JUDGE = "D:/tools/raptor/.claude/skills/fable-parity/bin/ext_judge.py"
cap, date = sys.argv[1], sys.argv[2]
K = int(sys.argv[3]) if len(sys.argv) > 3 else 3
LABELS = ["A", "B", "C", "D", "E"]

w = json.load(open(cap, encoding="utf-8"))
res = w.get("result", w)
if isinstance(res, str): res = json.loads(res)

def judge(task, answers):
    p = subprocess.run([sys.executable, EXT_JUDGE, "--timeout", "300"],
                       input=json.dumps({"task": task, "answers": answers}),
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=360)
    line = (p.stdout or "").strip().splitlines()[-1] if (p.stdout or "").strip() else ""
    try: return json.loads(line) if line else {"ok": False}
    except Exception: return {"ok": False}

records = []
stable_count = 0
for t in res.get("per_task", []):
    arms = [a for a in t.get("arms", []) if a.get("answer")]
    if len(arms) < 2:
        continue
    winners = []
    for k in range(K):
        rot = k % len(arms)
        rotated = arms[rot:] + arms[:rot]
        lab = {}
        answers = []
        for i, a in enumerate(rotated):
            lab[LABELS[i]] = a["arm"]
            answers.append({"id": LABELS[i], "text": a["answer"]})
        v = judge(t["prompt"], answers)
        winners.append(lab.get(v.get("best")) if v.get("ok") else None)
    uniq = set(w for w in winners if w)
    stable = len(uniq) == 1 and None not in winners
    if stable: stable_count += 1
    # majority winner
    from collections import Counter
    maj = Counter(w for w in winners if w).most_common(1)
    records.append({"id": t["id"], "archetype": t.get("archetype"),
                    "winners_across_runs": winners, "stable": stable,
                    "majority_winner": maj[0][0] if maj else None,
                    "majority_frac": f"{maj[0][1]}/{K}" if maj else "0/0"})

out = {"K": K, "n_tasks": len(records), "n_stable": stable_count,
       "records": records}
json.dump(out, open(os.path.join(EVAL, f"qual-parity-{date}", "judge-stability.json"), "w",
                    encoding="utf-8", newline="\n"), ensure_ascii=False, indent=2)
print(f"self-consistency: {stable_count}/{len(records)} tasks had an IDENTICAL winner across all {K} shuffled judgings")
for r in records:
    print(f"  {r['id']} ({r['archetype']}): winners={r['winners_across_runs']} -> "
          f"{'STABLE' if r['stable'] else 'unstable'} (majority {r['majority_winner']} {r['majority_frac']})")

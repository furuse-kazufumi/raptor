#!/usr/bin/env python3
"""Blind-judge the quality parity capture and aggregate.

For each task: take the 3 arm answers, DETERMINISTICALLY shuffle to anonymous labels
(rotation by task index removes fixed position bias while staying reproducible), run
the independent codex judge (ext_judge.py), map the ranking back to models, and tally
which model won. Freezes everything (perishable Fable answers + rankings + reasons).

Usage: judge_qualcap.py <capture_result.json> <date e.g. 2026-07-05>
"""
import json, os, subprocess, sys

HERE = "C:/dev/tools/raptor/.claude/skills/fable-parity/bin"
EXT_JUDGE = os.path.join(HERE, "ext_judge.py")
EVAL = "C:/dev/tools/raptor/.claude/skills/fable-parity/eval"

cap_path, date = sys.argv[1], sys.argv[2]
w = json.load(open(cap_path, encoding="utf-8"))
res = w.get("result", w)
if isinstance(res, str):
    res = json.loads(res)
per_task = res.get("per_task", [])

outdir = os.path.join(EVAL, f"qual-parity-{date}")
os.makedirs(outdir, exist_ok=True)
LABELS = ["A", "B", "C", "D", "E"]

def run_judge(task_prompt, answers):
    payload = json.dumps({"task": task_prompt, "answers": answers})
    p = subprocess.run([sys.executable, EXT_JUDGE, "--timeout", "300"], input=payload,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=360)
    line = (p.stdout or "").strip().splitlines()[-1] if (p.stdout or "").strip() else ""
    try:
        return json.loads(line) if line else {"ok": False, "reason": "no output"}
    except Exception as e:
        return {"ok": False, "reason": "parse: " + str(e), "raw": line[:200]}

wins = {}
pairwise = {"scaffold_beats_opusraw": 0, "fable_beats_opusraw": 0, "scaffold_beats_fable": 0, "judged": 0}
records = []

for idx, t in enumerate(per_task):
    arms = [a for a in t.get("arms", []) if a.get("answer")]
    if len(arms) < 2:
        records.append({"id": t["id"], "skipped": "fewer than 2 arms available"}); continue
    rot = idx % len(arms)
    rotated = arms[rot:] + arms[:rot]                 # deterministic shuffle
    labelmap = {}                                     # label -> model/arm
    judge_answers = []
    for i, a in enumerate(rotated):
        lab = LABELS[i]
        labelmap[lab] = a["arm"]
        judge_answers.append({"id": lab, "text": a["answer"]})

    verdict = run_judge(t["prompt"], judge_answers)
    rec = {"id": t["id"], "archetype": t.get("archetype"), "labelmap": labelmap, "judge": verdict}
    if verdict.get("ok"):
        ranking_models = [labelmap[l] for l in verdict["ranking"]]
        winner = labelmap[verdict["best"]] if verdict.get("best") in labelmap else ranking_models[0]
        rec["ranking_models"] = ranking_models
        rec["winner"] = winner
        wins[winner] = wins.get(winner, 0) + 1
        pos = {m: i for i, m in enumerate(ranking_models)}   # lower = better
        pairwise["judged"] += 1
        if "opus+deep-reason" in pos and "opus-raw" in pos and pos["opus+deep-reason"] < pos["opus-raw"]:
            pairwise["scaffold_beats_opusraw"] += 1
        if "fable-raw" in pos and "opus-raw" in pos and pos["fable-raw"] < pos["opus-raw"]:
            pairwise["fable_beats_opusraw"] += 1
        if "opus+deep-reason" in pos and "fable-raw" in pos and pos["opus+deep-reason"] < pos["fable-raw"]:
            pairwise["scaffold_beats_fable"] += 1
    records.append(rec)

# freeze full results (incl. perishable fable answers)
json.dump({"per_task": per_task, "judgments": records, "wins": wins, "pairwise": pairwise},
          open(os.path.join(outdir, "results.json"), "w", encoding="utf-8", newline="\n"),
          ensure_ascii=False, indent=2)

# report
L = []
L.append(f"# Quality parity — blind independent judge — {date}\n")
L.append("5 quality-discriminating open-ended tasks. 3 arms (opus-raw, fable-raw, opus+deep-reason+ext). "
         "A blind, independent **codex (gpt-5.4)** judge ranked the anonymized answers per task "
         "(non-Anthropic → independent of both Opus and Fable). Fable answers frozen here are perishable.\n")
L.append("## Wins (ranked #1 by the blind judge)\n")
for m in ["fable-raw", "opus-raw", "opus+deep-reason"]:
    L.append(f"- **{m}**: {wins.get(m,0)} / {pairwise['judged']}")
L.append("")
L.append("## Pairwise (out of tasks judged)\n")
L.append(f"- opus+deep-reason ranked ABOVE opus-raw: {pairwise['scaffold_beats_opusraw']} / {pairwise['judged']}  "
         "(does the scaffold improve on a raw Opus pass?)")
L.append(f"- fable-raw ranked ABOVE opus-raw: {pairwise['fable_beats_opusraw']} / {pairwise['judged']}  "
         "(is there an Opus→Fable single-pass quality gap at all?)")
L.append(f"- opus+deep-reason ranked ABOVE fable-raw: {pairwise['scaffold_beats_fable']} / {pairwise['judged']}  "
         "(does the scaffold reach/exceed Fable?)")
L.append("")
L.append("## Per task\n")
L.append("| task | archetype | judge ranking (best→worst) | winner |")
L.append("|---|---|---|---|")
for r in records:
    if r.get("ranking_models"):
        L.append(f"| {r['id']} | {r.get('archetype','')} | {' > '.join(r['ranking_models'])} | **{r['winner']}** |")
    else:
        L.append(f"| {r['id']} | {r.get('archetype','')} | (judge failed: {r.get('judge',{}).get('reason','?')}) | - |")
L.append("")
L.append("## Honest caveats\n")
L.append("- Single blind judge (codex), single run per arm, N=5 → INDICATIVE, not statistically powered. "
         "A quality ranking is softer than an objective key; codex is one family's judgment.\n"
         "- This measures single-pass QUALITY (depth/coverage/subtle-correctness), the axis where an Opus↔Fable "
         "gap could appear (objective correctness was at ceiling for both — see harder-stageA). "
         "Do NOT report 'measured parity' beyond exactly what these counts say.")
open(os.path.join(outdir, "report.md"), "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")
print("froze ->", outdir)
print("wins:", json.dumps(wins))
print("pairwise:", json.dumps(pairwise))

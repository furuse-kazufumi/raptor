#!/usr/bin/env python3
"""2-way blind gap judge: fable-raw (frozen) vs opus-raw, per task, via the blind
independent codex judge. Cheap way to expand the Opus<->Fable single-pass QUALITY
gap measurement to tasks where only the (perishable) fable arm was captured up front.

Usage: judge_2way.py <opus_raw_capture.json> <date>
  - fable answers read from  eval/qual-parity-<date>/fable-frozen/<id>.md
  - opus-raw answers read from the given capture json (per_task[].arms[arm=opus-raw])
"""
import json, os, re, subprocess, sys

EVAL = "C:/dev/tools/raptor/.claude/skills/fable-parity/eval"
EXT_JUDGE = "C:/dev/tools/raptor/.claude/skills/fable-parity/bin/ext_judge.py"
cap_path, date = sys.argv[1], sys.argv[2]
frozen_dir = os.path.join(EVAL, f"qual-parity-{date}", "fable-frozen")

def read_fable(tid):
    p = os.path.join(frozen_dir, f"{tid}.md")
    if not os.path.exists(p): return None
    txt = open(p, encoding="utf-8").read()
    m = re.split(r"## Fable answer\s*\n", txt, maxsplit=1)
    return m[1].strip() if len(m) == 2 else None

def read_task_prompt(tid):
    p = os.path.join(frozen_dir, f"{tid}.md")
    txt = open(p, encoding="utf-8").read()
    m = re.search(r"## Task\s*\n(.*?)\n## Fable answer", txt, re.DOTALL)
    return m.group(1).strip() if m else ""

w = json.load(open(cap_path, encoding="utf-8"))
res = w.get("result", w)
if isinstance(res, str): res = json.loads(res)
opus = {t["id"]: next((a.get("answer") for a in t.get("arms", []) if a["arm"] == "opus-raw"), None)
        for t in res.get("per_task", [])}

def judge(task, answers):
    payload = json.dumps({"task": task, "answers": answers})
    p = subprocess.run([sys.executable, EXT_JUDGE, "--timeout", "300"], input=payload,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=360)
    line = (p.stdout or "").strip().splitlines()[-1] if (p.stdout or "").strip() else ""
    try: return json.loads(line) if line else {"ok": False}
    except Exception: return {"ok": False}

records = []; wins = {"fable-raw": 0, "opus-raw": 0}; judged = 0
for idx, tid in enumerate(sorted(opus.keys())):
    fab = read_fable(tid); op = opus[tid]
    if not fab or not op:
        records.append({"id": tid, "skipped": "missing arm"}); continue
    # deterministic shuffle: even idx -> fable=A, odd -> opus=A
    if idx % 2 == 0:
        answers = [{"id": "A", "text": fab}, {"id": "B", "text": op}]; lab = {"A": "fable-raw", "B": "opus-raw"}
    else:
        answers = [{"id": "A", "text": op}, {"id": "B", "text": fab}]; lab = {"A": "opus-raw", "B": "fable-raw"}
    v = judge(read_task_prompt(tid), answers)
    rec = {"id": tid, "labelmap": lab, "judge": v}
    if v.get("ok"):
        winner = lab.get(v.get("best"))
        ranking = [lab[l] for l in v["ranking"]]
        rec["winner"] = winner; rec["ranking"] = ranking
        wins[winner] = wins.get(winner, 0) + 1; judged += 1
    records.append(rec)

out = {"comparison": "fable-raw vs opus-raw (single-pass quality)", "judged": judged, "wins": wins, "records": records}
json.dump(out, open(os.path.join(EVAL, f"qual-parity-{date}", "gap-2way-results.json"), "w", encoding="utf-8", newline="\n"),
          ensure_ascii=False, indent=2)
print("2-way gap judged:", judged, "wins:", json.dumps(wins))
for r in records:
    if r.get("winner"): print(" ", r["id"], "->", r["winner"], "(", " > ".join(r["ranking"]), ")")
    else: print(" ", r["id"], "-> skipped/failed")

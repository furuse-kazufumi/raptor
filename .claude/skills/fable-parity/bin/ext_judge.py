#!/usr/bin/env python3
"""Blind independent quality judge for fable-parity parity measurement.

Ranks N anonymized candidate answers to a hard open-ended task using an EXTERNAL,
non-Anthropic model family (OpenAI Codex / gpt-5.4) — independent of BOTH the Opus
and Fable arms it is judging, so the parity verdict is not self-graded (the skill's
eval methodology requires a non-Fable, non-Opus judge).

Input (stdin JSON or --file):
  {"task": "...", "criteria": "optional override",
   "answers": [{"id":"A","text":"..."}, {"id":"B","text":"..."}, ...]}
Output (stdout JSON one line):
  {"model":"codex","ranking":["B","A","C"],"best":"B","reasons":{...},"ok":true}
Fail-closed: any invocation/parse failure -> {"ok": false, ...} (never a silent bogus ranking).
"""
import argparse, json, os, re, shutil, subprocess, sys

MARK_START = "<<<VERDICT>>>"
MARK_END = "<<<ENDVERDICT>>>"
DEFAULT_CRITERIA = ("correctness of subtle/technical points, depth and rigor of reasoning, "
                    "coverage of edge cases, and absence of errors or hand-waving. Do NOT reward "
                    "length or confident tone per se — a shorter answer that is correct and complete "
                    "beats a long one that is padded or wrong.")


def build_prompt(task, answers, criteria):
    parts = [
        "You are a STRICT, IMPARTIAL judge. Below is a hard open-ended TASK and several ANONYMIZED "
        "candidate answers (you do NOT know which model wrote which). Rank them from BEST to WORST on: "
        + criteria,
        "",
        "You must actually assess the technical substance — reward the answer that gets the subtle points "
        "right and covers the space, and penalize plausible-but-wrong claims, missing cases, and hand-waving.",
        "",
        "TASK:",
        task,
        "",
    ]
    for a in answers:
        parts.append(f"===== CANDIDATE {a['id']} =====")
        parts.append(a["text"])
        parts.append("")
    ids = ",".join('"%s"' % a["id"] for a in answers)
    parts += [
        "Output NOTHING except a single line in EXACTLY this form (a JSON object between the markers, "
        "ranking = the candidate ids best-first, best = the top id, reasons = a one-sentence justification per id):",
        MARK_START + '{"ranking":[' + ids + '],"best":"<id>","reasons":{"<id>":"...", "...":"..."}}' + MARK_END,
    ]
    return "\n".join(parts)


def extract(text, valid_ids):
    if not text:
        return None
    m = re.search(re.escape(MARK_START) + r"(.*?)" + re.escape(MARK_END), text, re.DOTALL)
    payload = m.group(1).strip() if m else None
    if not payload:
        i = text.rfind(MARK_START)
        if i != -1:
            payload = text[i + len(MARK_START):].strip()
    if not payload:
        # last resort: a bare object containing "ranking"
        m2 = re.search(r'\{.*?"ranking".*?\}', text, re.DOTALL)
        payload = m2.group(0) if m2 else None
    if not payload:
        return None
    try:
        obj = json.loads(payload)
    except Exception:
        return None
    ranking = obj.get("ranking")
    if not isinstance(ranking, list) or sorted(ranking) != sorted(valid_ids):
        return None  # must be a permutation of the given ids
    return {"ranking": ranking, "best": obj.get("best") or ranking[0],
            "reasons": obj.get("reasons") if isinstance(obj.get("reasons"), dict) else {}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=None)
    ap.add_argument("--timeout", type=int, default=300)
    args = ap.parse_args()

    raw = open(args.file, encoding="utf-8").read() if args.file else sys.stdin.read()
    try:
        data = json.loads(raw or "{}")
    except Exception as e:
        print(json.dumps({"ok": False, "reason": "input parse error: " + str(e)})); return 0

    task = data.get("task", "")
    answers = data.get("answers", [])
    criteria = data.get("criteria") or DEFAULT_CRITERIA
    answers = [a for a in answers if a.get("id") and a.get("text")]
    if not task or len(answers) < 2:
        print(json.dumps({"ok": False, "reason": "need a task and >=2 answers with id+text"})); return 0

    ids = [a["id"] for a in answers]
    prompt = build_prompt(task, answers, criteria)

    exe = shutil.which("codex")
    if not exe:
        print(json.dumps({"ok": False, "reason": "codex CLI not found"})); return 0

    env = dict(os.environ)
    for k in ("TERMINAL", "EDITOR", "VISUAL", "BROWSER", "PAGER"):
        env.pop(k, None)
    try:
        p = subprocess.run([exe, "exec", "-s", "read-only"], input=prompt,
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=args.timeout, env=env)
        out = (p.stdout or "") + "\n" + (p.stderr or "")
    except subprocess.TimeoutExpired:
        print(json.dumps({"ok": False, "reason": "judge timed out after %ds" % args.timeout})); return 0
    except Exception as e:
        print(json.dumps({"ok": False, "reason": "invocation error: " + str(e)[:200]})); return 0

    v = extract(out, ids)
    if v is None:
        tail = out.strip().splitlines()[-3:] if out.strip() else []
        print(json.dumps({"ok": False, "reason": "no parseable ranking", "raw_tail": " | ".join(tail)[:300]})); return 0

    print(json.dumps({"model": "codex", "ranking": v["ranking"], "best": v["best"],
                      "reasons": v["reasons"], "ok": True}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

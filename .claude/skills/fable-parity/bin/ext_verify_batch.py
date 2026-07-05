#!/usr/bin/env python3
"""Batch heterogeneous adversarial verification for fable-parity.

Runs ext_verify.py across N claims x M external model families in parallel and
aggregates into a per-claim verdict. The point is DE-CORRELATION: the verify
signal comes from model families other than the Opus generator, so a
confident-but-wrong Opus claim that would survive an Opus-only majority can still
be caught by an independent family.

Aggregation (per claim), refute-by-default:
  - Consider only backend results with ok=true (a real model judgment).
  - If ANY ok=true backend says "refuted"  -> claim REFUTED.
  - Else if >=1 ok=true backend says "survives" -> claim SURVIVES.
  - Else (no backend produced a usable judgment) -> UNVERIFIED (flagged, never
    silently "survives"; infra failure must not masquerade as verification).

Input (stdin JSON or --file):
  {"claims": ["...", "..."], "context": "optional", "models": ["codex"], "voters": 1}
Output (stdout JSON):
  {"summary": {...}, "per_claim": [{claim, verdict, by_model:[{model,verdict,reason,ok}], ...}]}

Usage:
  echo '{"claims":["17 is prime","21 is prime"],"models":["codex"]}' \
      | py -3.11 ext_verify_batch.py
  py -3.11 ext_verify_batch.py --file claims.json
"""
import argparse, concurrent.futures as cf, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
EXT_VERIFY = os.path.join(HERE, "ext_verify.py")


def run_one(model, claim, context, timeout):
    """Invoke ext_verify.py for one (model, claim). Returns the parsed dict."""
    try:
        p = subprocess.run(
            [sys.executable, EXT_VERIFY, "--model", model, "--claim", claim,
             "--context", context or "", "--timeout", str(timeout)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout + 30,
        )
        line = (p.stdout or "").strip().splitlines()[-1] if (p.stdout or "").strip() else ""
        obj = json.loads(line) if line else {}
        obj.setdefault("model", model)
        obj.setdefault("verdict", "refuted")
        obj.setdefault("ok", False)
        return obj
    except Exception as e:
        return {"model": model, "verdict": "refuted", "ok": False,
                "reason": "batch runner error: " + str(e)[:200]}


def aggregate(results):
    """results: list of per-model dicts for ONE claim -> aggregated verdict."""
    usable = [r for r in results if r.get("ok")]
    if not usable:
        return "unverified"
    if any(r.get("verdict") == "refuted" for r in usable):
        return "refuted"
    return "survives"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=None, help="JSON input file (else stdin)")
    ap.add_argument("--timeout", type=int, default=180, help="per-call timeout (s)")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    raw = open(args.file, encoding="utf-8").read() if args.file else sys.stdin.read()
    try:
        data = json.loads(raw or "{}")
    except Exception as e:
        print(json.dumps({"error": "input JSON parse error: " + str(e)}))
        return 2

    claims = data.get("claims") or []
    context = data.get("context", "")
    models = data.get("models") or ["codex"]
    voters = int(data.get("voters", 1))
    if not claims:
        print(json.dumps({"error": "no claims provided"}))
        return 2

    # Build the task grid: claim x model x voter.
    tasks = []
    for ci, claim in enumerate(claims):
        for model in models:
            for _v in range(max(1, voters)):
                tasks.append((ci, model, claim))

    results_by_claim = {ci: [] for ci in range(len(claims))}
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(run_one, model, claim, context, args.timeout): ci
                for (ci, model, claim) in tasks}
        for fut in cf.as_completed(futs):
            ci = futs[fut]
            results_by_claim[ci].append(fut.result())

    per_claim = []
    counts = {"refuted": 0, "survives": 0, "unverified": 0}
    for ci, claim in enumerate(claims):
        rs = results_by_claim[ci]
        verdict = aggregate(rs)
        counts[verdict] += 1
        per_claim.append({
            "claim": claim,
            "verdict": verdict,
            "by_model": [{"model": r.get("model"), "verdict": r.get("verdict"),
                          "reason": r.get("reason", ""), "ok": bool(r.get("ok"))} for r in rs],
        })

    print(json.dumps({
        "summary": {
            "n_claims": len(claims), "models": models, "voters": voters,
            "counts": counts,
            "note": "heterogeneous, refute-by-default: a claim is REFUTED if any independent "
                    "non-Opus family refutes it; UNVERIFIED means no backend produced a usable "
                    "judgment (infra failure) and must be treated as not-verified, not as pass.",
        },
        "per_claim": per_claim,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

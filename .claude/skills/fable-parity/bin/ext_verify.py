#!/usr/bin/env python3
"""External (non-Opus) adversarial verifier for fable-parity.

Why: the whole skill rests on the generation-verification gap, but if every agent
is Opus the verifier shares the generator's blind spots (correlated errors -> a
confident wrong answer can win the vote). The 2026-07-05 baseline made this
concrete (Opus-only synthesis shipped a degenerate answer). Routing the verify
signal to a DIFFERENT model family (OpenAI Codex / Google Gemini) de-correlates it.

What: takes a single load-bearing CLAIM (+ optional CONTEXT), asks an external CLI
model to REFUTE it (default-refuted if uncertain), and emits a clean one-line JSON
verdict on stdout:
    {"model": "...", "verdict": "survives"|"refuted", "reason": "...", "ok": true}
Fail-closed: any invocation/parse failure -> verdict "refuted" (never silently
"survives"), matching the skill's refute-by-default posture.

Usage:
    ext_verify.py --model codex   --claim "<claim>" [--context "<ctx>"] [--timeout 180]
    echo '{"claim":"...","context":"..."}' | ext_verify.py --model gemini --stdin

Backends (verified present 2026-07-05): codex (codex-cli 0.135.0, gpt-5.4),
gemini, copilot. codex is the proven default.
"""
import argparse, json, os, re, shutil, subprocess, sys

MARK_START = "<<<VERDICT>>>"
MARK_END = "<<<ENDVERDICT>>>"

PROMPT_TMPL = (
    "You are an INDEPENDENT adversarial verifier from a different model family than the author. "
    "You did not write the claim and owe it no charity. Try hard to REFUTE the CLAIM below using "
    "evidence, a counterexample, or a logical flaw. If you cannot verify it, or you are uncertain, "
    "treat it as REFUTED (default-refuted). Do not accept a claim just because it sounds plausible.\n\n"
    "CLAIM:\n{claim}\n\n"
    "CONTEXT (may be empty):\n{context}\n\n"
    "Output NOTHING except a single line in EXACTLY this form (no code fences, no extra text):\n"
    '{start}{{"verdict":"survives"|"refuted","reason":"<one concise sentence>"}}{end}\n'
    "Use verdict \"survives\" ONLY if you genuinely could not refute it after a real attempt."
).replace("{start}", MARK_START).replace("{end}", MARK_END)


def build_cmd(model, prompt):
    """Return argv for the chosen backend, or None if the CLI is not installed.

    Resolve the launcher via shutil.which so Windows npm shims (codex.CMD etc.)
    are found and runnable by full path without shell=True (avoids prompt-quoting
    injection risk)."""
    exe = shutil.which(model)
    if not exe:
        return None
    if model == "codex":
        # read-only sandbox, never prompt for approval; prompt as positional arg.
        return [exe, "exec", "-s", "read-only", prompt]
    if model == "gemini":
        return [exe, "-p", prompt]   # gemini CLI non-interactive
    if model == "copilot":
        return [exe, "-p", prompt]
    raise ValueError("unknown model: " + model)


def extract_verdict(text):
    """Pull the marked JSON out of noisy CLI output. Returns dict or None."""
    if not text:
        return None
    m = re.search(re.escape(MARK_START) + r"(.*?)" + re.escape(MARK_END), text, re.DOTALL)
    payload = None
    if m:
        payload = m.group(1).strip()
    else:
        # tolerate a model that dropped the end marker: take everything after start marker
        i = text.find(MARK_START)
        if i != -1:
            payload = text[i + len(MARK_START):].strip()
            # cut at first newline-block if it rambled
            payload = payload.split("\n")[0].strip()
    if not payload:
        # last resort: find a bare {...} with a "verdict" key
        m2 = re.search(r'\{[^{}]*"verdict"\s*:\s*"(survives|refuted)"[^{}]*\}', text)
        if m2:
            payload = m2.group(0)
    if not payload:
        return None
    try:
        obj = json.loads(payload)
    except Exception:
        # extract fields by regex if JSON is slightly malformed
        vm = re.search(r'"verdict"\s*:\s*"(survives|refuted)"', payload)
        rm = re.search(r'"reason"\s*:\s*"([^"]*)"', payload)
        if not vm:
            return None
        obj = {"verdict": vm.group(1), "reason": rm.group(1) if rm else ""}
    v = str(obj.get("verdict", "")).strip().lower()
    if v not in ("survives", "refuted"):
        return None
    return {"verdict": v, "reason": str(obj.get("reason", ""))[:500]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="codex", choices=["codex", "gemini", "copilot"])
    ap.add_argument("--claim", default=None)
    ap.add_argument("--context", default="")
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--stdin", action="store_true", help="read {claim,context} JSON from stdin")
    args = ap.parse_args()

    claim, context = args.claim, args.context
    if args.stdin:
        try:
            data = json.loads(sys.stdin.read() or "{}")
            claim = data.get("claim", claim)
            context = data.get("context", context or "")
        except Exception as e:
            print(json.dumps({"model": args.model, "verdict": "refuted", "ok": False,
                              "reason": "stdin parse error: " + str(e)}))
            return 0

    if not claim:
        print(json.dumps({"model": args.model, "verdict": "refuted", "ok": False,
                          "reason": "no claim provided"}))
        return 0

    prompt = PROMPT_TMPL.format(claim=claim, context=context or "(none)")
    argv = build_cmd(args.model, prompt)
    if argv is None:
        print(json.dumps({"model": args.model, "verdict": "refuted", "ok": False,
                          "reason": "%s CLI not found on PATH" % args.model}))
        return 0

    # Sanitize env of shell-evaluable vars (untrusted-repo discipline).
    env = dict(os.environ)
    for k in ("TERMINAL", "EDITOR", "VISUAL", "BROWSER", "PAGER"):
        env.pop(k, None)

    try:
        p = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=args.timeout, env=env)
        out = (p.stdout or "") + "\n" + (p.stderr or "")
    except subprocess.TimeoutExpired:
        print(json.dumps({"model": args.model, "verdict": "refuted", "ok": False,
                          "reason": "external verifier timed out after %ds" % args.timeout}))
        return 0
    except FileNotFoundError:
        print(json.dumps({"model": args.model, "verdict": "refuted", "ok": False,
                          "reason": "%s CLI not found" % args.model}))
        return 0
    except Exception as e:
        print(json.dumps({"model": args.model, "verdict": "refuted", "ok": False,
                          "reason": "invocation error: " + str(e)[:200]}))
        return 0

    verdict = extract_verdict(out)
    if verdict is None:
        # fail-closed: no parseable verdict = default-refuted
        tail = out.strip().splitlines()[-3:] if out.strip() else []
        print(json.dumps({"model": args.model, "verdict": "refuted", "ok": False,
                          "reason": "no parseable verdict from external model",
                          "raw_tail": " | ".join(tail)[:300]}))
        return 0

    print(json.dumps({"model": args.model, "verdict": verdict["verdict"],
                      "reason": verdict["reason"], "ok": True}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

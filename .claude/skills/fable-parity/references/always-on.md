# fable-parity "always-on" — running Opus in orchestration mode by default

Answer to: *「Opus で常にオーケストラで動作する環境を整えることは可能か？」*

**Short answer: yes — but only in the form that is actually useful.**
Two readings of "常に (always)":

1. **Unconditional-always** — orchestrate *every* turn, no gate. Technically trivial
   to force, but this skill's own `eval/run-parity-eval.js` measured a **CEILING
   effect**: on tasks Opus already solves single-pass, fan-out + verify add **cost,
   not correctness**. Forcing it everywhere burns tokens and wall-clock on trivial
   turns and can even *lose* (self-critique with no external signal can flip a right
   answer to wrong). **Do not do this.** It contradicts the skill's core gate and the
   honest-disclosure discipline.

2. **Always-*gated* auto-routing** — the gate is **evaluated on every substantive
   turn**, and orchestration fires **only** when the task clears it (stakes AND
   single-pass-risk AND a verification asymmetry). Trivial/lookup turns pass straight
   through. This is achievable and is what "整える" should mean. It gives the *feel*
   of "always on" (you never forget to reach for it) without the ceiling-effect tax.

This file sets up reading **#2**.

---

## The three layers

An always-gated environment needs all three; each covers a different failure:

| Layer | Mechanism | What it guarantees | If missing |
|---|---|---|---|
| **1. Enablement** | `/model opus` **+** `/effort ultracode` | The Workflow tool is allowed to fire the skill's JS workflows | Without ultracode, workflows can't run — only the manual Agent-dispatch fallback (`usage-on-opus.md §4`) works |
| **2. Trigger** | `UserPromptSubmit` hook `fable_parity_gate.py` (`FABLE_PARITY_ALWAYS=1`) | The gate is *evaluated every substantive turn* — mechanically, not by luck of recall | Auto-trigger is a soft LLM decision; easy to forget on a busy turn |
| **3. Discipline** | The 3-part gate in `SKILL.md` / `routing.md` Gate 0/1 | Only qualifying tasks consume orchestration; trivial ones don't | Degrades into reading #1 (unconditional) → ceiling-effect waste |

Why not classify hardness statically in the hook and auto-launch a workflow? Because
task difficulty isn't reliably decidable from the prompt text, and firing a workflow
has real cost. The hook does the cheap half (skip obviously-trivial turns) and hands
the expensive judgment (does the gate clear? which workflow?) to the model with the
full turn context. That division is deliberate.

---

## Turn it on

1. **Session model must be Opus** (the whole premise): `/model opus`, verify with `/model`.
   On the global Fable session this is unnecessary — Fable needs no scaffold; leave the
   gate off.
2. **Enable Workflow execution**: `/effort ultracode`.
3. **Enable the gate hook**: set the env toggle. In `.claude/raptor.env`, uncomment:
   ```sh
   export FABLE_PARITY_ALWAYS=1
   ```
   (or export it in the ccr launch environment). The `UserPromptSubmit` hook is already
   wired in `.claude/settings.json`; it is a **no-op until this env is set**, so wiring it
   is safe even on Fable sessions.

That's the whole setup. From then on, every substantive prompt gets a compact reminder
to run the gate; trivial turns (slash commands, short asks, `ls`/`cat`-shape) get nothing.

## Turn it off

Unset `FABLE_PARITY_ALWAYS` (or set it to `off`). The hook goes silent immediately; no
settings edit needed.

---

## Honesty caveats (unchanged from the skill)

- This buys **reliability and self-checking**, not new capability. It cannot recover
  missing knowledge, sub-coverage-floor answers, or verification-hard tasks with no
  asymmetry (see `SKILL.md` §正直な限界 and `principles.md`).
- **Never claim "Fable parity."** The always-on setup makes the scaffold *habitual*; it
  does not measure that Opus+scaffold equals a Fable pass. Measuring that still requires
  `eval/parity-eval.md` with an independent, non-Fable judge.
- The gate reminder itself costs a few tokens per substantive turn. That is the price of
  "never forget"; it is bounded (trivial turns are free) but not zero. If you dislike it,
  prefer explicit per-task invocation ("use fable-parity deep-reason on …") and leave the
  gate off.

## Files

- Hook: `.claude/hooks/fable_parity_gate.py` (self-tested; fail-open, exit 0 always).
- Wiring: `.claude/settings.json` → `hooks.UserPromptSubmit`.
- Toggle: `.claude/raptor.env` → `FABLE_PARITY_ALWAYS`.

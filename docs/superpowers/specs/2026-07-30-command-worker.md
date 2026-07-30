# CommandWorker — deterministic tool/command worker (implementation spec)

Status: **ready to implement** (fresh session). Goal: let the work-graph run a
shell command (e.g. a render script) and capture its produced artifact into
`out/worklog/<task_id>/`, so **autonomous re-render → dashboard gallery** works
(today only LLM workers exist; a render is not an LLM task). First real use:
onocollo mocap GIF re-render.

## Design (small — ~40 lines + routing + tests)

### Task spec format (for `tool` capability tasks)
`task.spec` is JSON describing the command:
```json
{
  "cmd": ["py","-3.11","scripts\\musculo_mascot.py","--dance","<bvh>","--out","<OUT>"],
  "cwd": "C:\\dev\\projects\\onocollo-complete",
  "env": {"PYTHONPATH": "C:\\dev\\projects\\onocollo-complete\\src"},
  "produces": "<OUT>",      // file the cmd writes; omit if it writes into <artifacts>/<id>/ directly
  "timeout": 900
}
```
Convention: the runner substitutes the literal token `<OUT>` in `cmd`/`produces`
with `out/worklog/<task_id>/result.<ext>` (or a fixed name), so the command
writes straight into the artifacts dir and the gallery picks it up. If `produces`
points elsewhere, the worker copies it into `out/worklog/<task_id>/`.

### `packages/worklog/workers.py` — add `CommandWorker`
```
class CommandWorker(Worker):
    model = "tool:command"; autonomous = True
    def run(self, task, artifacts_dir):
        import json, shutil, subprocess, time
        try: spec = json.loads(task["spec"])
        except Exception: return WorkerResult(False, self.model, task["id"], error="tool task spec must be JSON {cmd,cwd,produces,...}")
        out_dir = Path(artifacts_dir)/task["id"]; out_dir.mkdir(parents=True, exist_ok=True)
        out_token = str(out_dir/"result")            # <OUT> base (cmd appends ext, or use produces)
        sub = lambda s: s.replace("<OUT>", out_token) if isinstance(s,str) else s
        cmd = [sub(x) for x in spec["cmd"]]
        env = safe_env(); env.update(spec.get("env") or {})
        start=time.time()
        try:
            p = subprocess.run(cmd, cwd=spec.get("cwd") or None, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=float(spec.get("timeout",900)), env=env)
        except subprocess.TimeoutExpired: return WorkerResult(False, self.model, task["id"], error="command timeout")
        except Exception as exc: return WorkerResult(False, self.model, task["id"], error=f"{type(exc).__name__}: {exc}")
        dur=time.time()-start; tail=clean_output((p.stdout or "")+ (p.stderr or ""))[-2000:]
        produces = sub(spec.get("produces","")) if spec.get("produces") else None
        ref=None
        if produces and Path(produces).is_file():
            dst=out_dir/Path(produces).name
            if Path(produces).resolve()!=dst.resolve(): shutil.copy2(produces, dst)
            ref=str(dst)
        else:  # else: assume cmd wrote into out_dir; pick newest file there
            files=sorted(out_dir.glob("*"), key=lambda q:q.stat().st_mtime, reverse=True)
            ref=str(files[0]) if files else None
        if p.returncode!=0 and not ref:
            return WorkerResult(False, self.model, task["id"], error=f"exit {p.returncode}: {tail[-400:]}", duration=dur)
        return WorkerResult(True, self.model, task["id"], result_ref=ref, output=tail, duration=dur)
```
`make_worker`: add `if model == "tool:command": return CommandWorker()`.

### `packages/worklog/routing.py` + `validate.py`
- `validate.CAPABILITIES`: add `"tool"`.
- `routing.LOCAL_FIRST`: add `"tool": ["tool:command"]`; add `"tool"` to `HARDNESS`.
- `_is_local` already treats `tool:` as local (no session cost).

### Security (raptor rule)
List-arg subprocess only; NO shell string. `<OUT>` substitution is the only
templating. Commands are author-supplied (human/Claude-queued) → trusted; still
run under `safe_env()` + a timeout. Do not interpolate task text into a shell.

## First use — onocollo mocap re-render (autonomous)
Prereq once: `cd C:\dev\projects\onocollo-complete; py -3.11 scripts\fetch_cmu_dance.py` (BVH → assets\mocap).
Queue a tool task:
```
py -3.11 libexec/raptor-worklog add --project onocollo --capability tool \
  --title "onocollo mocap re-render" --spec '{"cmd":["py","-3.11","scripts\\musculo_mascot.py","--dance","<BVH>","--out","<OUT>.gif"],"cwd":"C:\\dev\\projects\\onocollo-complete","env":{"PYTHONPATH":"C:\\dev\\projects\\onocollo-complete\\src"},"produces":"<OUT>.gif","timeout":1200}'
```
Then `rap -Serve` (or `raptor-worklog run-once`) → CommandWorker runs the render →
GIF lands in `out/worklog/<id>/` → refresh `rap -Web` gallery. GL note: if mujoco
GL fails, add `"MUJOCO_GL":"osmesa"` to env.

## Tests (`packages/worklog/tests/test_workers.py`, no heavy deps)
- CommandWorker runs a trivial real subprocess that writes a file into `<OUT>`,
  asserts ok + result_ref exists + points inside artifacts/<id>/.
  e.g. cmd = `["py","-3.11","-c","import sys;open(sys.argv[1],'w').write('ok')","<OUT>.txt"]`, produces `<OUT>.txt`.
- Bad JSON spec → ok=False.
- routing: `route(["tool"], False, ["tool:command"]) == "tool:command"`; `make_worker("tool:command")` is CommandWorker.

## Acceptance
A `tool` task with the onocollo render command, processed autonomously, produces
a fresh GIF that appears in the `rap -Web` gallery — the "既存GIF経由" demo becomes
genuine autonomous re-render.

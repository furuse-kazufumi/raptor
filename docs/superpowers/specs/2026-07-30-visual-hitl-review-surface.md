# Visual HITL Review Surface for the Work-Graph — design options (2026-07-30)

Status: **design / options** (not yet built; captured for a fresh-session build).
Inter-project coupling decisions are the **user's** to make (memory
`feedback_fullsense_project_priority`: "プロジェクト間の結合はユーザーが判断、Claude は
勝手に結合しない") — this doc lays out options, it does not commit to a merge.

## Goal

An llterm-inspired **control + review surface** that lets the human:
1. start interactively, give instructions, then **switch to autonomous** (already
   supported: queue tasks with `raptor-worklog add`, then `rp -Serve -Detach`);
2. **visually confirm image / video / SVG artifacts** produced by autonomous runs
   (onocollo/evis GIFs & mp4, musculo renders, plots, Mermaid/SVG diagrams);
3. approve / reject results (HITL), feeding the different-provider verify gate.

## Hard requirement → form factor

**Image + video inline review needs a browser.** A TUI (Textual) renders images
only via sixel/kitty (env-dependent) and cannot play video. So the media-review
part must be web; a TUI can host control/text but not the videos.

## Reusable building blocks (compose, don't reinvent)

| Piece | Reuse for |
|---|---|
| **work-graph** (`packages/worklog/`, built) | orchestration + durable state; tasks carry `result_ref` → the artifacts to review |
| **llove** (Textual HITL workbench: choice-points, approval bus, SVG/Mermaid/MD render, LLM arena) | the **HITL approve/reject flow** + scenario/choice structure |
| **llmesh** (on-prem LLM hub, MCP, multi-LLM, SPC) | optional: route worker **model access through llmesh** instead of raw ollama/codex (formal multi-LLM layer) |

## Options

- **A (recommended): new thin local web dashboard** `worklog-web`
  (`packages/worklog/web.py` + `libexec/raptor-worklog-web`, stdlib `http.server`,
  local-first, no external deps). One page:
  - work-graph status (tasks / ready / leased / done / escalation, from the store);
  - **artifact gallery**: scan `out/worklog/**` for `*.png|gif|jpg|svg|mp4|webm`,
    render inline (`<img>` / `<video>`), grouped by task, with the handoff summary;
  - HITL controls (v2): approve/reject (→ verify gate / mark done/failed),
    "go autonomous" button (→ `rp -Serve -Detach`), tail `driver.{out,err}.log`.
  - Borrows llove's HITL/approval *concepts*; keeps work-graph as backend; llmesh
    optional as the model layer.
- **B: extend llove** (Textual) as the front; media shown via a small companion
  web view it launches. Keeps everything in the llove app but splits media out.
- **C: fold into llmesh's MCP** surface (heavier; makes the hub the entry point).

## MVP (fresh session)

Read-only `worklog-web`: work-graph table + artifact gallery of `out/worklog`
media, served on `localhost:<port>`. Prove: run the driver → open the page →
see the produced GIFs/mp4/renders inline next to their task + handoff. Then add
HITL approve/reject + the `-Detach` launch button (v2).

## Honest constraints

- Local-first (FullSense): localhost server only, no external egress; media served
  from local `out/`.
- Video ⇒ browser (settled above).
- Any llove/llmesh coupling is the **user's** integration decision; default is a
  standalone `worklog-web` that *references* them, not a merge.
- The `-Detach` launch hook (bin/rp.ps1) is the seam the surface calls to go
  autonomous.

"""Local read-only web dashboard for the work-graph — visual HITL review.

Serves (localhost only, no egress) one page: work-graph status + an artifact
gallery that renders images / GIF / SVG / mp4 inline, so a human can visually
confirm what autonomous runs produced (onocollo/evis GIFs & mp4, renders, plots,
diagrams). Stdlib only. Launched via `rp -Web` / `raptor-worklog web`.

Security (raptor rule): the /artifact endpoint is fail-closed — it only serves
files that resolve to inside the artifacts dir; anything else is 403/404.
"""

from __future__ import annotations

import html
import http.server
import mimetypes
import os
import socketserver
import time
import urllib.parse
import webbrowser
from pathlib import Path

from .store import open_graph

_IMG_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp"}
_VID_EXT = {".mp4", ".webm", ".mov", ".m4v"}
_MEDIA_EXT = _IMG_EXT | _VID_EXT

# The page is rendered fresh per request, but a browser left open would sit on a
# stale snapshot — useless for watching an overnight autonomous run. Auto-reload
# instead, and stamp the render time so "is this current?" is answerable from the
# page itself. 0 disables (a long session on a slow link, or manual-only review).
AUTO_REFRESH_SECONDS = int(os.environ.get("WORKLOG_WEB_REFRESH", "30"))


def _find_media(artifacts_dir: Path) -> list[Path]:
    if not artifacts_dir.exists():
        return []
    return sorted(
        (p for p in artifacts_dir.rglob("*") if p.is_file() and p.suffix.lower() in _MEDIA_EXT),
        key=lambda p: p.stat().st_mtime, reverse=True,
    )


def _esc(s: object) -> str:
    return html.escape(str(s))


def _fmt_size(p: Path) -> str:
    n = p.stat().st_size
    return f"{n / 1_048_576:.1f} MB" if n >= 1_048_576 else f"{max(n // 1024, 1)} KB"


def _render_page(db_path: str, artifacts_dir: Path) -> str:
    wg = open_graph(db_path)
    try:
        tasks = wg.all_tasks()
        counts = wg.counts()
        esc = wg.escalation()
    finally:
        wg.close()
    media = _find_media(artifacts_dir)

    rows = []
    for t in tasks:
        rows.append(
            "<tr><td class=m>{id}</td><td><span class='st st-{status}'>{status}</span></td>"
            "<td>p{priority}</td><td>{project}</td><td>{title}</td><td class=m>{by}</td></tr>".format(
                id=_esc(t["id"]), status=_esc(t["status"]), priority=_esc(t["priority"]),
                project=_esc(t.get("project", "")), title=_esc(t["title"]),
                by=_esc(t.get("result_by") or ""),
            )
        )

    # A caption of "<task_id> / result.gif" identifies nothing — the id is a
    # timestamp-hash and almost every worker writes the same filename. Join each
    # artifact back to the task that produced it so the card says *what it is*.
    by_id = {t["id"]: t for t in tasks}
    cards = []
    for p in media:
        rel = p.relative_to(artifacts_dir).as_posix()
        url = "/artifact?path=" + urllib.parse.quote(rel)
        # the task dir is the FIRST path component (a worker may nest below it)
        task_id = rel.split("/")[0]
        t = by_id.get(task_id)
        if p.suffix.lower() in _VID_EXT:
            body = f"<video src='{_esc(url)}' controls preload=metadata></video>"
        else:
            body = f"<img src='{_esc(url)}' loading=lazy alt='{_esc(rel)}'>"

        title = t["title"] if t else "(no task in graph)"
        meta = []
        if t and t.get("project"):
            meta.append(_esc(t["project"]))
        if t and t.get("result_by"):
            meta.append(_esc(t["result_by"]))
        meta.append(_fmt_size(p))
        meta.append(time.strftime("%m/%d %H:%M", time.localtime(p.stat().st_mtime)))
        status = (
            f"<span class='st st-{_esc(t['status'])}'>{_esc(t['status'])}</span> " if t else ""
        )
        cards.append(
            f"<figure>{body}<figcaption>{status}<b>{_esc(title)}</b>"
            f"<div class=cmeta>{' · '.join(meta)}</div>"
            f"<div class=cid>{_esc(rel)}</div></figcaption></figure>"
        )

    counts_s = " · ".join(f"{k}:{v}" for k, v in counts.items() if v)
    banner = ""
    if esc.get("stalled"):
        banner = "<div class=alert>⚠ stalled — runnable work exists but nothing is running (human needed)</div>"
    # What is being worked on RIGHT NOW has no artifact yet, so it cannot show up
    # in the gallery — surface the leased set at the top or the board can't answer
    # "which one is it doing?" while a long sweep is mid-flight.
    running = [t for t in tasks if t["status"] == "leased"]
    if running:
        items = "".join(
            f"<li><b>{_esc(t['title'])}</b>"
            f"<div class=cmeta>{_esc(t.get('project') or '')} · {_esc(t.get('id'))}</div></li>"
            for t in running
        )
        banner += f"<div class=now>running now ({len(running)})<ul>{items}</ul></div>"

    refresh_tag = (
        f"<meta http-equiv=refresh content='{AUTO_REFRESH_SECONDS}'>"
        if AUTO_REFRESH_SECONDS > 0 else ""
    )
    refresh_note = (
        f"auto-refresh {AUTO_REFRESH_SECONDS}s" if AUTO_REFRESH_SECONDS > 0 else "manual reload"
    )

    return f"""<!doctype html><html lang=ja><head><meta charset=utf-8>
<meta name=viewport content='width=device-width,initial-scale=1'>{refresh_tag}
<title>work-graph board</title><style>
:root{{color-scheme:dark light}}
body{{font:14px/1.5 system-ui,'Segoe UI',sans-serif;margin:0;background:#111;color:#eee}}
header{{padding:12px 16px;background:#181818;border-bottom:1px solid #333;position:sticky;top:0}}
h1{{font-size:16px;margin:0 0 4px}} .sub{{color:#9aa;font-size:12px}}
main{{padding:16px;max-width:1200px;margin:0 auto}}
h2{{font-size:14px;color:#9df;border-bottom:1px solid #333;padding-bottom:4px;margin-top:24px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
td,th{{text-align:left;padding:4px 8px;border-bottom:1px solid #262626;vertical-align:top}}
.m{{font-family:ui-monospace,Consolas,monospace;color:#bbb;font-size:12px}}
.st{{padding:1px 7px;border-radius:10px;font-size:11px}}
.st-ready{{background:#1d3b53}} .st-leased{{background:#4a3a12}} .st-done{{background:#1e3a24}}
.st-failed{{background:#4a1e1e}} .st-blocked{{background:#3a1e3a}} .st-pending{{background:#2a2a2a}}
.gallery{{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px;margin-top:12px}}
figure{{margin:0;background:#181818;border:1px solid #2a2a2a;border-radius:8px;overflow:hidden}}
figure img,figure video{{width:100%;height:200px;object-fit:contain;background:#000;display:block}}
figcaption{{padding:6px 8px;font-size:11px;color:#9aa;word-break:break-word}}
figcaption b{{color:#eee;font-size:12px}}
.cmeta{{color:#8ab;margin-top:3px}}
.cid{{color:#667;font-family:ui-monospace,Consolas,monospace;font-size:10px;margin-top:2px;word-break:break-all}}
.alert{{background:#4a1e1e;padding:8px 12px;border-radius:6px;margin:12px 0}}
.now{{background:#1d3b53;padding:8px 12px;border-radius:6px;margin:12px 0;font-size:12px}}
.now ul{{margin:6px 0 0;padding-left:18px}} .now li{{margin:2px 0}}
.empty{{color:#778;padding:12px}}
</style></head><body>
<header><h1>work-graph board</h1>
<div class=sub>read-only visual review · {_esc(counts_s or "empty")}
· updated {time.strftime('%H:%M:%S')} · {refresh_note}</div></header>
<main>{banner}
<h2>Artifacts ({len(media)})</h2>
{'<div class=gallery>' + ''.join(cards) + '</div>' if cards else "<div class=empty>(no media in out/worklog yet — run a task that produces renders)</div>"}
<h2>Tasks ({len(tasks)})</h2>
<table><tr><th>id</th><th>status</th><th>pri</th><th>project</th><th>title</th><th>by</th></tr>
{''.join(rows) if rows else '<tr><td colspan=6 class=empty>(no tasks — seed the graph)</td></tr>'}
</table></main></body></html>"""


class _Handler(http.server.BaseHTTPRequestHandler):
    db_path = ""
    artifacts_dir = Path(".")

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        u = urllib.parse.urlparse(self.path)
        if u.path == "/":
            body = _render_page(self.db_path, self.artifacts_dir).encode("utf-8")
            self._send(200, body, "text/html; charset=utf-8")
            return
        if u.path == "/artifact":
            qs = urllib.parse.parse_qs(u.query)
            rel = (qs.get("path") or [""])[0]
            base = self.artifacts_dir.resolve()
            target = (base / rel).resolve()
            # fail-closed: only serve files that resolve to inside the artifacts dir
            if not (target == base or base in target.parents) or not target.is_file():
                self._send(403, b"forbidden", "text/plain")
                return
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            self._send(200, target.read_bytes(), ctype)
            return
        self._send(404, b"not found", "text/plain")

    def log_message(self, *a) -> None:  # quiet
        return


def serve(db_path, artifacts_dir, port: int = 8765, open_browser: bool = True) -> None:
    _Handler.db_path = str(db_path)
    _Handler.artifacts_dir = Path(artifacts_dir)
    with socketserver.TCPServer(("127.0.0.1", port), _Handler) as httpd:
        url = f"http://127.0.0.1:{port}/"
        print(f"[web] work-graph board: {url}  (Ctrl-C to stop)")
        if open_browser:
            try:
                webbrowser.open(url)
            except Exception:  # noqa: BLE001
                pass
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[web] stopped")

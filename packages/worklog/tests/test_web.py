"""Web dashboard: media discovery + page render (server path-safety is verified
live: /artifact rejects traversal with 403)."""

from packages.worklog import web
from packages.worklog.store import WorkGraph


def test_find_media_filters_by_extension(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "r.png").write_bytes(b"x")
    (tmp_path / "a" / "clip.mp4").write_bytes(b"x")
    (tmp_path / "a" / "notes.md").write_text("nope", encoding="utf-8")
    found = {p.name for p in web._find_media(tmp_path)}
    assert found == {"r.png", "clip.mp4"}  # .md excluded


def test_render_page_shows_tasks_and_media(tmp_path):
    db = tmp_path / "wg.db"
    g = WorkGraph(db)
    try:
        g.add_task(task_id="t1", title="render mascot", spec="s", project="p", capability=["codegen"])
    finally:
        g.close()
    art = tmp_path / "art"
    (art / "t1").mkdir(parents=True)
    (art / "t1" / "out.gif").write_bytes(b"gif")
    html = web._render_page(str(db), art)
    assert "work-graph board" in html
    assert "render mascot" in html          # task row
    assert "/artifact?path=" in html        # gallery links a media file
    assert "out.gif" in html

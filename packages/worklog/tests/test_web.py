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


def test_gallery_card_identifies_the_task_that_produced_it(tmp_path):
    """'<task_id> / result.gif' identifies nothing — the card must name the work."""
    db = tmp_path / "wg.db"
    g = WorkGraph(db)
    try:
        g.add_task(task_id="t1", title="onocollo chopsticks re-render", spec="s",
                   project="onocollo", capability=["tool"])
        g.lease("t1", owner="w1", model="tool:command")
        g.complete("t1", owner="w1", result_ref="r", result_by="tool:command")
    finally:
        g.close()
    art = tmp_path / "art"
    (art / "t1").mkdir(parents=True)
    (art / "t1" / "result.gif").write_bytes(b"g" * 2048)
    html = web._render_page(str(db), art)
    assert "onocollo chopsticks re-render" in html   # the title, not just the id
    assert "onocollo" in html                        # project
    assert "tool:command" in html                    # who produced it
    assert "2 KB" in html                            # size
    assert "t1/result.gif" in html                   # still shows the exact path


def test_board_surfaces_the_currently_running_task(tmp_path):
    """A leased task has no artifact yet, so the gallery can't show it — the board
    must still answer "which one is it working on?" mid-sweep."""
    db = tmp_path / "wg.db"
    g = WorkGraph(db)
    try:
        g.add_task(task_id="n1", title="llcore NAS: context sweep 2048/4096", spec="s",
                   project="llcore", capability=["tool"])
        g.add_task(task_id="n2", title="not started yet", spec="s", project="llcore",
                   capability=["tool"])
        g.lease("n1", owner="w1", model="tool:command")
    finally:
        g.close()
    html = web._render_page(str(db), tmp_path / "art")
    assert "running now (1)" in html
    assert "llcore NAS: context sweep 2048/4096" in html
    # the ready task must not be listed as running
    assert html.index("running now (1)") < html.index("Artifacts")
    banner = html[html.index("running now (1)"):html.index("Artifacts")]
    assert "not started yet" not in banner


def test_board_omits_running_banner_when_nothing_is_leased(tmp_path):
    db = tmp_path / "wg.db"
    g = WorkGraph(db)
    try:
        g.add_task(task_id="n1", title="idle task", spec="s", capability=["tool"])
    finally:
        g.close()
    assert "running now" not in web._render_page(str(db), tmp_path / "art")


def test_gallery_card_survives_an_artifact_with_no_task(tmp_path):
    """Smoke/manual files under the artifacts dir must not break the board."""
    db = tmp_path / "wg.db"
    WorkGraph(db).close()
    art = tmp_path / "art"
    (art / "_smoke").mkdir(parents=True)
    (art / "_smoke" / "test.svg").write_bytes(b"<svg/>")
    html = web._render_page(str(db), art)
    assert "(no task in graph)" in html
    assert "_smoke/test.svg" in html


def _page(tmp_path):
    db = tmp_path / "wg.db"
    WorkGraph(db).close()
    return web._render_page(str(db), tmp_path / "art")


def test_page_auto_refreshes_and_stamps_render_time(tmp_path, monkeypatch):
    """A browser left open on an overnight run must not sit on a stale snapshot,
    and the page must say when it was rendered so staleness is visible."""
    monkeypatch.setattr(web, "AUTO_REFRESH_SECONDS", 30)
    html = _page(tmp_path)
    assert "http-equiv=refresh content='30'" in html
    assert "auto-refresh 30s" in html
    assert "updated " in html


def test_auto_refresh_can_be_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "AUTO_REFRESH_SECONDS", 0)
    html = _page(tmp_path)
    assert "http-equiv=refresh" not in html
    assert "manual reload" in html

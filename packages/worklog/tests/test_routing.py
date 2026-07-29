"""Routing tests — local-first, on-prem boundary, availability."""

from packages.worklog import routing


def test_dominant_capability_picks_hardest():
    assert routing.dominant_capability(["triage", "reason"]) == "reason"
    assert routing.dominant_capability(["summarize", "triage"]) == "summarize"
    assert routing.dominant_capability([]) == routing.DEFAULT_CAPABILITY


def test_candidates_local_first():
    c = routing.candidates(["summarize"])
    assert c[0].startswith("ollama")  # local first
    assert "codex" in c


def test_candidates_on_prem_only_drops_cloud():
    c = routing.candidates(["codegen"], on_prem_only=True)
    assert all(m.startswith(("ollama", "tool:")) for m in c)
    assert "claude" not in c and "codex" not in c


def test_route_prefers_local_when_available():
    avail = ["ollama:qwen2.5:14b", "codex", "claude", "tool:deterministic"]
    assert routing.route(["summarize"], False, avail) == "ollama:qwen2.5:14b"


def test_route_escalates_when_local_absent():
    avail = ["codex", "claude", "tool:deterministic"]  # no ollama
    assert routing.route(["summarize"], False, avail) == "codex"


def test_route_reason_goes_to_claude():
    avail = ["ollama:qwen2.5:14b", "claude", "tool:deterministic"]
    assert routing.route(["reason"], False, avail) == "claude"


def test_route_on_prem_never_cloud():
    avail = ["claude", "codex", "tool:deterministic"]  # only cloud LLMs available
    # on_prem_only task cannot use them → None (must wait for a local model)
    assert routing.route(["codegen"], True, avail) is None


def test_route_none_when_nothing_available():
    assert routing.route(["reason"], False, []) is None


def test_route_matches_ollama_tag_suffix():
    # `ollama list` reports 'llama3.1:latest'; the table says 'ollama:llama3.1'.
    avail = ["ollama:llama3.1:latest", "ollama:qwen2.5:14b", "tool:deterministic"]
    assert routing.route(["triage"], False, avail) == "ollama:llama3.1:latest"


def test_autonomous_only():
    assert routing.autonomous_only(["triage"], False) is True
    assert routing.autonomous_only(["summarize"], False) is True
    assert routing.autonomous_only(["reason"], False) is False   # claude → human-gated
    assert routing.autonomous_only(["codegen"], True) is True    # on-prem → local ollama

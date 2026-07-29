"""Invariant / graph-algorithm tests."""

import pytest

from packages.worklog import validate
from packages.worklog.validate import InvariantError


def test_no_cycle_linear():
    deps = {"c": ["b"], "b": ["a"], "a": []}
    assert validate.has_cycle(deps) is False


def test_simple_cycle():
    deps = {"a": ["b"], "b": ["a"]}
    assert validate.has_cycle(deps) is True


def test_self_loop_is_cycle():
    assert validate.has_cycle({"a": ["a"]}) is True


def test_unknown_targets_ignored():
    # depends on a node that isn't in the graph → not a cycle
    deps = {"a": ["ghost"], "b": ["a"]}
    assert validate.has_cycle(deps) is False


def test_would_create_cycle():
    deps = {"a": [], "b": ["a"]}
    # a -> b would close a<->b cycle (b already depends on a)
    assert validate.would_create_cycle(deps, "a", "b") is True
    # c -> a is fine
    assert validate.would_create_cycle(deps, "c", "a") is False
    # self edge
    assert validate.would_create_cycle(deps, "a", "a") is True


def test_topological_order():
    deps = {"c": ["b"], "b": ["a"], "a": []}
    order = validate.topological_order(deps)
    assert order.index("a") < order.index("b") < order.index("c")


def test_topological_order_raises_on_cycle():
    with pytest.raises(InvariantError):
        validate.topological_order({"a": ["b"], "b": ["a"]})


def test_is_local_model():
    assert validate.is_local_model("ollama:qwen2.5:14b") is True
    assert validate.is_local_model("ollama") is True
    assert validate.is_local_model("claude") is False
    assert validate.is_local_model("codex") is False
    assert validate.is_local_model(None) is False


def test_provider_of():
    assert validate.provider_of("ollama:qwen2.5-coder:32b") == "ollama"
    assert validate.provider_of("claude") == "claude"
    assert validate.provider_of("codex") == "codex"


def test_check_capabilities_rejects_unknown():
    with pytest.raises(InvariantError):
        validate.check_capabilities(["triage", "not-a-real-cap"])
    assert validate.check_capabilities(["triage", "reason"]) == ["triage", "reason"]


def test_check_status_rejects_unknown():
    with pytest.raises(InvariantError):
        validate.check_status("RUNNING")
    assert validate.check_status("ready") == "ready"

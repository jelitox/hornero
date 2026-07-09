"""Dispatch bridge: brief rendering, mock determinism, resolution rules.

Must pass with multicoders ABSENT from the venv.
"""

import sys
import types

import pytest

from hornero.adapters.dispatch import MockBackend, MulticodersDispatch, brief_from_spec
from hornero.lifecycle import parse_spec
from hornero.ports import DispatchPort

SPEC_TEXT = """---
spec: SPEC-002
title: Weekly digest email
status: approved
kind: new_feature
created: 2026-07-07
sources: [sig-a]
supersedes: []
acceptance_criteria:
  - "pytest tests/digest -q"
  - "manual: email renders in Thunderbird"
---

# SPEC-002 — Weekly digest email

Send a digest. See ADR-001 for the scheduling decision.
"""

ALLOW = ["pytest", "ruff", "mypy", "python"]


def _doc(tmp_path):
    p = tmp_path / "SPEC-002-digest.md"
    p.write_text(SPEC_TEXT, encoding="utf-8")
    return parse_spec(p)


def test_brief_from_spec_inlines_referenced_adrs(tmp_path):
    decisions = tmp_path / "decisions"
    decisions.mkdir()
    (decisions / "ADR-001-scheduling.md").write_text(
        "# ADR-001 — cron over queue\n", encoding="utf-8"
    )
    (decisions / "ADR-002-unrelated.md").write_text("# ADR-002\n", encoding="utf-8")
    brief = brief_from_spec(_doc(tmp_path), str(tmp_path), ALLOW, decisions)
    assert brief["spec_id"] == "SPEC-002" and brief["kind"] == "new_feature"
    assert "cron over queue" in brief["description"]
    assert "ADR-002" not in brief["description"]
    assert brief["acceptance_criteria"][0] == "pytest tests/digest -q"


def test_brief_broken_criteria_raise(tmp_path):
    doc = _doc(tmp_path)
    broken = doc.__class__(**{**doc.__dict__, "acceptance_criteria": ["   "]})
    with pytest.raises(ValueError):
        brief_from_spec(broken, str(tmp_path), ALLOW, tmp_path / "decisions")


def test_mock_backend_deterministic(tmp_path):
    from hornero.flight import TraceWriter

    brief = brief_from_spec(_doc(tmp_path), str(tmp_path), ALLOW, tmp_path / "d")
    a = MockBackend(tmp_path, counter=1).run(
        brief, TraceWriter(tmp_path, "r-a", "dispatch:mock", clock=lambda: 0.0)
    )
    b = MockBackend(tmp_path, counter=1).run(
        brief, TraceWriter(tmp_path, "r-b", "dispatch:mock", clock=lambda: 0.0)
    )
    assert a == b
    assert a["status"] == "completed"
    assert a["pr_url"] == "https://example.invalid/pr/SPEC-002-1"
    assert a["branch"] == "hornero/SPEC-002"


def test_mock_resolution_default(tmp_path):
    d = MulticodersDispatch(["mock"], tmp_path)
    assert d.backend_name == "mock"


def test_cli_backend_absent_yields_needs_human(tmp_path):
    d = MulticodersDispatch(["cli"], tmp_path)
    brief = brief_from_spec(_doc(tmp_path), str(tmp_path), ALLOW, tmp_path / "d")
    result = d.dispatch(brief)
    assert result["status"] == "needs_human" and result["pr_url"] is None
    from hornero.flight import read_trace

    events = read_trace(tmp_path, "run-spec-002")
    assert any(e["kind"] == "error" and "not installed" in e["summary"]
               for e in events)


def test_api_never_a_fallback(tmp_path, monkeypatch):
    # simulate multicoders being installed
    import importlib.machinery
    for name in ("multicoders", "multicoders.backends"):
        mod = types.ModuleType(name)
        mod.__spec__ = importlib.machinery.ModuleSpec(name, None)
        monkeypatch.setitem(sys.modules, name, mod)
    # api listed AFTER a failed backend: must be skipped, resolution falls
    # through to mock
    d = MulticodersDispatch(["nonexistent", "api", "mock"], tmp_path)
    assert d.backend_name == "mock"
    # api as the explicit FIRST choice is honored (resolves to the pending-
    # integration stub, not to mock)
    d2 = MulticodersDispatch(["api"], tmp_path)
    assert d2.backend_name == "api"


def test_empty_or_unusable_order_yields_needs_human(tmp_path):
    d = MulticodersDispatch([], tmp_path)
    brief = brief_from_spec(_doc(tmp_path), str(tmp_path), ALLOW, tmp_path / "d")
    assert d.dispatch(brief)["status"] == "needs_human"


def test_protocol_conformance(tmp_path):
    assert isinstance(MulticodersDispatch(["mock"], tmp_path), DispatchPort)

"""RepoTracker: upsert / transition / comment tests."""

import pytest

from hornero.adapters.repo_tracker import RepoTracker, UnknownRefError
from hornero.lifecycle import IllegalTransition, SpecParseError
from hornero.ports import TrackerPort

SPEC_TEXT = """---
spec: SPEC-002
title: Something
status: proposed
kind: enhancement
created: 2026-07-06
sources: []
supersedes: []
acceptance_criteria: []
---

# SPEC-002 — Something

Body.

## Log

- 2026-07-06 — drafted.
"""


def _repo(tmp_path, text=SPEC_TEXT):
    specs = tmp_path / "specs"
    specs.mkdir()
    (specs / "SPEC-002-something.md").write_text(text, encoding="utf-8")
    return specs


def _tracker(specs):
    return RepoTracker(specs, clock=lambda: "2026-07-07")


def test_upsert_returns_spec_id(tmp_path):
    specs = _repo(tmp_path)
    ref = _tracker(specs).upsert(str(specs / "SPEC-002-something.md"))
    assert ref == "SPEC-002"


def test_upsert_rejects_unparseable(tmp_path):
    bad = tmp_path / "SPEC-009-bad.md"
    bad.write_text("no frontmatter here", encoding="utf-8")
    with pytest.raises(SpecParseError):
        _tracker(tmp_path).upsert(str(bad))


def test_transition_edits_only_status_line(tmp_path):
    specs = _repo(tmp_path)
    path = specs / "SPEC-002-something.md"
    before = path.read_text(encoding="utf-8").splitlines()
    _tracker(specs).transition("SPEC-002", "approved")
    after = path.read_text(encoding="utf-8").splitlines()
    changed = [(a, b) for a, b in zip(before, after) if a != b]
    assert changed == [("status: proposed", "status: approved")]
    assert len(before) == len(after)


def test_illegal_transition_raises(tmp_path):
    specs = _repo(tmp_path)
    with pytest.raises(IllegalTransition):
        _tracker(specs).transition("SPEC-002", "done")


def test_unknown_ref_raises_and_creates_nothing(tmp_path):
    specs = _repo(tmp_path)
    tracker = _tracker(specs)
    with pytest.raises(UnknownRefError):
        tracker.transition("SPEC-999", "approved")
    with pytest.raises(UnknownRefError):
        tracker.comment("SPEC-999", "hello")
    assert sorted(p.name for p in specs.iterdir()) == ["SPEC-002-something.md"]


def test_comment_appends_to_log_section(tmp_path):
    specs = _repo(tmp_path)
    _tracker(specs).comment("SPEC-002", "build dispatched (r-1).")
    text = (specs / "SPEC-002-something.md").read_text(encoding="utf-8")
    assert "- 2026-07-06 — drafted.\n- 2026-07-07 — build dispatched (r-1).\n" in text


def test_comment_inserts_before_next_heading(tmp_path):
    text = SPEC_TEXT + "\n## Appendix\n\nStuff.\n"
    specs = _repo(tmp_path, text)
    _tracker(specs).comment("SPEC-002", "noted.")
    out = (specs / "SPEC-002-something.md").read_text(encoding="utf-8")
    assert out.index("noted.") < out.index("## Appendix")
    assert "- 2026-07-07 — noted.\n\n## Appendix" in out


def test_comment_creates_log_section_if_absent(tmp_path):
    text = SPEC_TEXT.split("## Log")[0]
    specs = _repo(tmp_path, text)
    _tracker(specs).comment("SPEC-002", "first note.")
    out = (specs / "SPEC-002-something.md").read_text(encoding="utf-8")
    assert out.endswith("## Log\n\n- 2026-07-07 — first note.\n")


def test_protocol_conformance(tmp_path):
    assert isinstance(_tracker(tmp_path), TrackerPort)

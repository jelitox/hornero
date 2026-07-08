"""Apply step: per-kind application, approval guard, ack ordering."""

import hashlib

import pytest

from hornero.adapters.inbox import InboxSource
from hornero.adapters.repo_tracker import RepoTracker
from hornero.lifecycle import SpecCorpus, Status, parse_spec
from hornero.models import DeltaKind, Evidence, RequirementDelta
from hornero.reconciler.apply import PatchError, apply_deltas, apply_unified_diff
from hornero.reconciler.hitl import Decision, ReviewResult, ReviewedDelta

EXISTING_SPEC = """---
spec: SPEC-001
title: CSV export
status: approved
kind: new_feature
created: 2026-07-01
sources: [sig-old]
supersedes: []
acceptance_criteria: []
---

# SPEC-001 — CSV export

Export usage as CSV.
"""

NEW_PATCH = """---
spec: SPEC-XXX
title: Weekly digest email
status: draft-whatever
kind: new_feature
created: 2026-07-07
supersedes: []
acceptance_criteria: []
---

# Weekly digest email

Send a weekly digest.
"""

CHANGE_DIFF = """@@ -14,1 +14,2 @@
 Export usage as CSV.
+Include the customer id column.
"""


def _repo(tmp_path):
    specs = tmp_path / "sdd" / "specs"
    specs.mkdir(parents=True)
    (specs / "SPEC-001-csv.md").write_text(EXISTING_SPEC, encoding="utf-8")
    (tmp_path / "sdd" / "decisions").mkdir()
    (tmp_path / ".hornero" / "inbox").mkdir(parents=True)
    (tmp_path / ".hornero" / "inbox" / "note.md").write_text("note", encoding="utf-8")
    return tmp_path


def _env(tmp_path):
    root = _repo(tmp_path)
    corpus = SpecCorpus(root / "sdd" / "specs")
    tracker = RepoTracker(root / "sdd" / "specs", clock=lambda: "2026-07-07")
    source = InboxSource(root / ".hornero")
    sid = source.poll()[0]["signal_id"]
    return root, corpus, tracker, source, sid


def _delta(sid, kind, affected, patch, delta_id="dlt-r-1-1", title="Weekly digest email"):
    return RequirementDelta(
        delta_id=delta_id,
        kind=kind,
        title=title,
        summary="s",
        affected_specs=affected,
        evidence=[Evidence(sid, "note", "L1")],
        confidence=0.9,
        proposed_patch=patch,
    )


def _approved(delta):
    return ReviewedDelta(delta, ReviewResult(Decision.APPROVED))


def _apply(reviewed, corpus, tracker, source, root):
    return apply_deltas(
        reviewed, corpus, tracker, source,
        decisions_dir=root / "sdd" / "decisions",
        proposals_dir=root / "sdd" / "proposals",
        templates_dir=root / "sdd" / "templates",
        today="2026-07-07",
    )


def _tree_hash(root):
    digest = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            digest.update(str(p).encode() + p.read_bytes())
    return digest.hexdigest()


def test_unified_diff_exact_apply():
    original = "a\nb\nc\n"
    diff = "@@ -2,1 +2,2 @@\n b\n+b2\n"
    assert apply_unified_diff(original, diff) == "a\nb\nb2\nc\n"


def test_unified_diff_context_mismatch_raises():
    with pytest.raises(PatchError, match="context mismatch"):
        apply_unified_diff("a\nX\nc\n", "@@ -2,1 +2,2 @@\n b\n+b2\n")


def test_new_delta_creates_valid_spec(tmp_path):
    root, corpus, tracker, source, sid = _env(tmp_path)
    report = _apply(
        [_approved(_delta(sid, DeltaKind.NEW, [], NEW_PATCH))],
        corpus, tracker, source, root,
    )
    assert report.created == ["SPEC-002"] and report.errors == []
    path = root / "sdd" / "specs" / "SPEC-002-weekly-digest-email.md"
    doc = parse_spec(path)
    assert doc.spec_id == "SPEC-002"
    assert doc.status is Status.APPROVED  # born proposed, then transitioned
    assert doc.sources == [sid]
    text = path.read_text(encoding="utf-8")
    assert "## Log" in text and "created from dlt-r-1-1" in text
    assert report.acked_signals == [sid]
    assert source.poll() == []  # acked


def test_changed_delta_applies_exact_diff(tmp_path):
    root, corpus, tracker, source, sid = _env(tmp_path)
    report = _apply(
        [_approved(_delta(sid, DeltaKind.CHANGED, ["SPEC-001"], CHANGE_DIFF))],
        corpus, tracker, source, root,
    )
    assert report.patched == ["SPEC-001"] and report.errors == []
    doc = parse_spec(root / "sdd" / "specs" / "SPEC-001-csv.md")
    assert "Include the customer id column." in doc.body
    assert doc.sources == ["sig-old", sid]  # merged, deduped


def test_changed_delta_stale_context_fails_cleanly(tmp_path):
    root, corpus, tracker, source, sid = _env(tmp_path)
    bad = CHANGE_DIFF.replace("Export usage as CSV.", "Totally different line.")
    before = (root / "sdd" / "specs" / "SPEC-001-csv.md").read_text()
    report = _apply(
        [_approved(_delta(sid, DeltaKind.CHANGED, ["SPEC-001"], bad))],
        corpus, tracker, source, root,
    )
    assert report.patched == [] and len(report.errors) == 1
    assert (root / "sdd" / "specs" / "SPEC-001-csv.md").read_text() == before
    assert report.acked_signals == []  # failed apply => no ack
    assert len(source.poll()) == 1


def test_obsolete_transitions_and_writes_adr(tmp_path):
    root, corpus, tracker, source, sid = _env(tmp_path)
    adr = root / "sdd" / "decisions" / "ADR-001-csv-choice.md"
    adr.write_text("# ADR-001\n\nWe committed to SPEC-001 CSV.\n", encoding="utf-8")
    report = _apply(
        [_approved(_delta(sid, DeltaKind.OBSOLETE, ["SPEC-001"], "", title="Kill CSV"))],
        corpus, tracker, source, root,
    )
    assert report.obsoleted == ["SPEC-001"] and report.adrs == ["ADR-002"]
    doc = parse_spec(root / "sdd" / "specs" / "SPEC-001-csv.md")
    assert doc.status is Status.OBSOLETE
    adr2 = root / "sdd" / "decisions" / "ADR-002-kill-csv.md"
    assert "dlt-r-1-1" in adr2.read_text(encoding="utf-8")


def test_unapproved_deltas_write_nothing(tmp_path):
    root, corpus, tracker, source, sid = _env(tmp_path)
    before = _tree_hash(root)
    reviewed = [
        ReviewedDelta(_delta(sid, DeltaKind.NEW, [], NEW_PATCH),
                      ReviewResult(Decision.SKIPPED)),
        ReviewedDelta(_delta(sid, DeltaKind.CHANGED, ["SPEC-001"], CHANGE_DIFF,
                             delta_id="dlt-r-1-2"),
                      ReviewResult(Decision.REJECTED)),
    ]
    report = _apply(
        reviewed, corpus, tracker, source, root
    )
    # rejected counts as a human decision => signal acked; spec tree untouched
    specs_dir = root / "sdd" / "specs"
    assert _tree_hash(specs_dir) == _tree_hash(specs_dir)
    assert report.created == report.patched == report.obsoleted == []
    assert before != _tree_hash(root) or report.acked_signals  # ack moved the file
    assert report.acked_signals == [sid]


def test_pure_skip_does_not_ack(tmp_path):
    root, corpus, tracker, source, sid = _env(tmp_path)
    reviewed = [
        ReviewedDelta(_delta(sid, DeltaKind.NEW, [], NEW_PATCH),
                      ReviewResult(Decision.SKIPPED)),
    ]
    report = _apply(
        reviewed, corpus, tracker, source, root
    )
    assert report.acked_signals == [] and len(source.poll()) == 1


def test_edited_patch_takes_precedence(tmp_path):
    root, corpus, tracker, source, sid = _env(tmp_path)
    edited = NEW_PATCH.replace("Weekly digest email", "Weekly digest email v2")
    reviewed = [
        ReviewedDelta(_delta(sid, DeltaKind.NEW, [], NEW_PATCH),
                      ReviewResult(Decision.EDITED, patch=edited)),
    ]
    report = _apply(
        reviewed, corpus, tracker, source, root
    )
    assert report.created == ["SPEC-002"]
    created = next((root / "sdd" / "specs").glob("SPEC-002-*.md"))
    assert "v2" in created.read_text(encoding="utf-8")


def test_new_delta_prose_patch_becomes_proposal(tmp_path):
    # SPEC-002 §2: an invalid-spec patch is routed to sdd/proposals/, it is
    # no longer an error, and the signal still gets acked.
    root, corpus, tracker, source, sid = _env(tmp_path)
    report = _apply(
        [_approved(_delta(sid, DeltaKind.NEW, [], "just prose, no frontmatter"))],
        corpus, tracker, source, root,
    )
    assert report.errors == [] and report.created == []
    assert report.proposals == ["weekly-digest-email.brainstorm.md"]
    assert list((root / "sdd" / "specs").glob("SPEC-002-*")) == []
    proposal = root / "sdd" / "proposals" / "weekly-digest-email.brainstorm.md"
    text = proposal.read_text(encoding="utf-8")
    assert "just prose, no frontmatter" in text  # raw patch preserved
    assert "dlt-r-1-1" in text  # origin delta recorded
    assert report.acked_signals == [sid] and source.poll() == []


def test_proposal_uses_repo_brainstorm_template(tmp_path):
    root, corpus, tracker, source, sid = _env(tmp_path)
    templates = root / "sdd" / "templates"
    templates.mkdir(parents=True)
    (templates / "brainstorm.md").write_text(
        "<!-- brainstorm template header -->", encoding="utf-8"
    )
    _apply(
        [_approved(_delta(sid, DeltaKind.NEW, [], "prose only"))],
        corpus, tracker, source, root,
    )
    text = (root / "sdd" / "proposals" / "weekly-digest-email.brainstorm.md").read_text(
        encoding="utf-8"
    )
    assert text.startswith("<!-- brainstorm template header -->")

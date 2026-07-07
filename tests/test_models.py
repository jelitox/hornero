"""Invariant + verbatim-check tests for the RequirementDelta model."""

import pytest

from hornero.models import DeltaKind, Evidence, RequirementDelta, verify_evidence


def _delta(**kw):
    base = dict(
        delta_id="dlt-r1-1",
        kind=DeltaKind.NEW,
        title="t",
        summary="s",
        affected_specs=[],
        evidence=[Evidence("sig-a", "export as CSV", "L4")],
        confidence=0.9,
        proposed_patch="...",
    )
    base.update(kw)
    return RequirementDelta(**base)


def test_evidence_required():
    with pytest.raises(ValueError, match="evidence"):
        _delta(evidence=[])


def test_new_iff_no_affected_specs():
    with pytest.raises(ValueError, match="NEW iff"):
        _delta(kind=DeltaKind.NEW, affected_specs=["SPEC-002"])
    with pytest.raises(ValueError, match="NEW iff"):
        _delta(kind=DeltaKind.CHANGED, affected_specs=[])


def test_confidence_range():
    with pytest.raises(ValueError, match="confidence"):
        _delta(confidence=1.5)
    with pytest.raises(ValueError, match="confidence"):
        _delta(confidence=-0.1)


def test_excerpt_bounds():
    with pytest.raises(ValueError, match="non-empty"):
        Evidence("sig-a", "", "L1")
    with pytest.raises(ValueError, match="exceeds"):
        Evidence("sig-a", "x" * 501, "L1")
    Evidence("sig-a", "x" * 500, "L1")  # boundary OK


def test_verbatim_substring_check():
    d = _delta()
    assert verify_evidence(d, {"sig-a": "we should export as CSV monthly"}) == []
    mismatches = verify_evidence(d, {"sig-a": "we should export as PDF monthly"})
    assert mismatches == d.evidence


def test_single_character_difference_is_mismatch():
    d = _delta(evidence=[Evidence("sig-a", "export as CSV", "L4")])
    assert verify_evidence(d, {"sig-a": "export as CSv"}) == d.evidence


def test_unknown_signal_id_is_mismatch():
    d = _delta()
    assert verify_evidence(d, {}) == d.evidence


def test_partial_mismatch_reports_only_bad_items():
    good = Evidence("sig-a", "export as CSV", "L4")
    bad = Evidence("sig-a", "fabricated quote", "L9")
    d = _delta(evidence=[good, bad])
    assert verify_evidence(d, {"sig-a": "please export as CSV"}) == [bad]


def test_duplicate_kind_constructs():
    d = _delta(kind=DeltaKind.DUPLICATE, affected_specs=["SPEC-001"])
    assert d.kind is DeltaKind.DUPLICATE

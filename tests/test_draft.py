"""Drafting pipeline: grounded drafts survive, everything else drops + logs."""

import json

import pytest

from hornero.lifecycle import SpecCorpus
from hornero.memory.knowledge import TokenOverlapKnowledge
from hornero.memory.ledger import Ledger
from hornero.models import DeltaKind
from hornero.ports import Signal
from hornero.reconciler.draft import draft_deltas
from hornero.reconciler.testing import FakeLLM, UnexpectedPromptError

SIGNAL_TEXT = """Meeting 2026-07-06.
We need to export monthly usage as CSV so finance can reconcile invoices.
Also drop the old XML feed, nobody uses it.
"""

SIG: Signal = {
    "signal_id": "sig-20260706-abc123",
    "kind": "meeting_notes",
    "path": "/x/note.md",
    "received_at": 0.0,
}


def _delta_json(**over):
    item = {
        "kind": "new",
        "title": "CSV export",
        "summary": "Finance needs a monthly CSV export.",
        "affected_specs": [],
        "evidence": [
            {
                "signal_id": "sig-20260706-abc123",
                "excerpt": "export monthly usage as CSV",
                "locator": "L2",
            }
        ],
        "confidence": 0.9,
        "proposed_patch": "---\nspec: SPEC-XXX\n---\nbody",
    }
    item.update(over)
    return item


def _run(tmp_path, response: str):
    ledger = Ledger(tmp_path / "ledger.db")
    llm = FakeLLM({"export monthly usage": response})
    corpus = SpecCorpus(tmp_path / "specs")
    knowledge = TokenOverlapKnowledge([])
    deltas = draft_deltas(SIG, SIGNAL_TEXT, corpus, knowledge, llm, ledger, "r-1", 5.0)
    return deltas, ledger


def test_grounded_draft_survives(tmp_path):
    deltas, ledger = _run(tmp_path, json.dumps({"deltas": [_delta_json()]}))
    assert len(deltas) == 1
    d = deltas[0]
    assert d.delta_id == "dlt-r-1-1"
    assert d.kind is DeltaKind.NEW
    assert ledger.dropped_drafts() == []


def test_fabricated_excerpt_dropped_and_logged(tmp_path):
    bad = _delta_json(
        evidence=[{"signal_id": "sig-20260706-abc123",
                   "excerpt": "export monthly usage as PDF", "locator": "L2"}]
    )
    deltas, ledger = _run(tmp_path, json.dumps({"deltas": [bad]}))
    assert deltas == []
    drops = ledger.dropped_drafts("r-1")
    assert len(drops) == 1 and drops[0]["reason"] == "evidence_mismatch"
    assert "PDF" in drops[0]["payload_json"]


def test_malformed_json_dropped_and_logged(tmp_path):
    deltas, ledger = _run(tmp_path, "sure! here are the deltas you asked for")
    assert deltas == []
    drops = ledger.dropped_drafts("r-1")
    assert len(drops) == 1 and drops[0]["reason"] == "parse_error"


def test_invariant_violation_dropped_and_logged(tmp_path):
    bad = _delta_json(kind="new", affected_specs=["SPEC-001"])
    deltas, ledger = _run(tmp_path, json.dumps({"deltas": [bad]}))
    assert deltas == []
    assert ledger.dropped_drafts("r-1")[0]["reason"] == "invariant_violation"


def test_missing_key_is_parse_error_for_that_item_only(tmp_path):
    broken = {"kind": "new", "summary": "no title"}
    ok = _delta_json()
    deltas, ledger = _run(tmp_path, json.dumps({"deltas": [broken, ok]}))
    assert len(deltas) == 1 and deltas[0].delta_id == "dlt-r-1-2"
    assert ledger.dropped_drafts("r-1")[0]["reason"] == "parse_error"


def test_mixed_batch_partial_survival_and_ids_deterministic(tmp_path):
    ok1 = _delta_json()
    fabricated = _delta_json(
        title="ghost",
        evidence=[{"signal_id": "sig-20260706-abc123",
                   "excerpt": "totally invented", "locator": "L9"}],
    )
    ok2 = _delta_json(
        kind="duplicate",
        title="dup of CSV",
        affected_specs=["SPEC-001"],
        evidence=[{"signal_id": "sig-20260706-abc123",
                   "excerpt": "drop the old XML feed", "locator": "L3"}],
    )
    response = json.dumps({"deltas": [ok1, fabricated, ok2]})
    a, _ = _run(tmp_path, response)
    b, _ = _run(tmp_path, response)
    assert [d.delta_id for d in a] == ["dlt-r-1-1", "dlt-r-1-3"]
    assert [(d.delta_id, d.title) for d in a] == [(d.delta_id, d.title) for d in b]


def test_fakellm_raises_on_unexpected_prompt(tmp_path):
    llm = FakeLLM({"nothing matches this": "{}"})
    with pytest.raises(UnexpectedPromptError):
        draft_deltas(
            SIG, SIGNAL_TEXT, SpecCorpus(tmp_path), TokenOverlapKnowledge([]),
            llm, Ledger(tmp_path / "l.db"), "r-1", 0.0,
        )

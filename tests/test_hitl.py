"""HITL gate: fail-closed + decision-flow tests (non-interactive by construction)."""

from hornero.models import DeltaKind, Evidence, RequirementDelta
from hornero.reconciler.hitl import (
    ApprovalChannel,
    Decision,
    ReviewResult,
    TerminalChannel,
    gate,
)


def _delta(kind=DeltaKind.NEW, affected=None, **kw):
    base = dict(
        delta_id="dlt-r-1-1",
        kind=kind,
        title="t",
        summary="s",
        affected_specs=[] if affected is None else affected,
        evidence=[Evidence("sig-a", "quote", "L1")],
        confidence=0.8,
        proposed_patch="PATCH",
    )
    base.update(kw)
    return RequirementDelta(**base)


class ScriptedChannel:
    def __init__(self, results):
        self.results = list(results)
        self.seen = []

    def review(self, delta, diff_text):
        self.seen.append((delta.delta_id, diff_text))
        return self.results.pop(0)


def test_no_channel_means_all_skipped():
    deltas = [_delta(), _delta(kind=DeltaKind.CHANGED, affected=["SPEC-001"],
                              delta_id="dlt-r-1-2")]
    reviewed = gate(deltas, None)
    assert [r.result.decision for r in reviewed] == [Decision.SKIPPED] * 2
    assert all(r.delta.status == "proposed" for r in reviewed)  # nothing mutated


def test_non_tty_refuses_to_open(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert TerminalChannel.open() is None


def test_duplicate_never_presented():
    channel = ScriptedChannel([ReviewResult(Decision.APPROVED)])
    dup = _delta(kind=DeltaKind.DUPLICATE, affected=["SPEC-001"])
    ok = _delta(delta_id="dlt-r-1-2")
    reviewed = gate([dup, ok], channel)
    assert channel.seen == [("dlt-r-1-2", "PATCH")]  # duplicate never shown
    assert reviewed[0].result.decision is Decision.SKIPPED
    assert reviewed[1].result.decision is Decision.APPROVED


def test_scripted_approve_reject_edit_skip():
    results = [
        ReviewResult(Decision.APPROVED),
        ReviewResult(Decision.REJECTED),
        ReviewResult(Decision.EDITED, patch="EDITED PATCH"),
        ReviewResult(Decision.SKIPPED),
    ]
    deltas = [_delta(delta_id=f"dlt-r-1-{i}") for i in range(1, 5)]
    reviewed = gate(deltas, ScriptedChannel(results))
    decisions = [r.result.decision for r in reviewed]
    assert decisions == [
        Decision.APPROVED, Decision.REJECTED, Decision.EDITED, Decision.SKIPPED,
    ]
    assert reviewed[2].result.patch == "EDITED PATCH"


def test_terminal_edit_without_editor_falls_back_to_reject(monkeypatch):
    monkeypatch.delenv("EDITOR", raising=False)
    channel = TerminalChannel()
    answers = iter(["x", "", "e"])  # junk + empty re-prompt, then edit
    monkeypatch.setattr(channel, "_in", lambda _prompt: next(answers))
    result = channel.review(_delta(), "PATCH")
    assert result.decision is Decision.REJECTED and result.patch is None


def test_terminal_approve_flow(monkeypatch):
    channel = TerminalChannel()
    monkeypatch.setattr(channel, "_in", lambda _prompt: "a")
    assert channel.review(_delta(), "PATCH").decision is Decision.APPROVED


def test_scripted_channel_satisfies_protocol():
    assert isinstance(ScriptedChannel([]), ApprovalChannel)

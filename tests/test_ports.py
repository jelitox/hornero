"""Structural conformance tests for the SPEC-001 §7 ports."""

from hornero.ports import (
    BuildBrief,
    BuildResult,
    DispatchPort,
    Signal,
    SignalSource,
    TrackerPort,
)


class _FakeSource:
    def poll(self) -> list[Signal]:
        return []

    def ack(self, signal_id: str) -> None: ...


class _FakeTracker:
    def upsert(self, spec_path: str) -> str:
        return "SPEC-001"

    def transition(self, ref: str, status: str) -> None: ...

    def comment(self, ref: str, body: str) -> None: ...


class _FakeDispatch:
    def dispatch(self, brief: BuildBrief) -> BuildResult:
        return {
            "status": "completed",
            "pr_url": None,
            "branch": None,
            "log_path": "/dev/null",
        }


def test_signal_source_is_runtime_checkable():
    assert isinstance(_FakeSource(), SignalSource)


def test_tracker_port_is_runtime_checkable():
    assert isinstance(_FakeTracker(), TrackerPort)


def test_dispatch_port_is_runtime_checkable():
    assert isinstance(_FakeDispatch(), DispatchPort)


def test_non_conforming_object_rejected():
    assert not isinstance(object(), SignalSource)
    assert not isinstance(object(), TrackerPort)
    assert not isinstance(object(), DispatchPort)


def test_signal_typeddict_fields():
    sig: Signal = {
        "signal_id": "sig-20260706-a1",
        "kind": "meeting_notes",
        "path": "/tmp/x.md",
        "received_at": 0.0,
    }
    assert set(sig) == {"signal_id", "kind", "path", "received_at"}

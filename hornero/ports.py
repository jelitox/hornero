"""Stable ports (SPEC-001 §7).

The three protocols below are the only seams between hornero core and any
environment. Core never imports an adapter; adapters are resolved from
``.hornero/config.yaml``. Field names and types are the public contract —
changing them is a spec change, not a refactor.
"""

from typing import Protocol, TypedDict, runtime_checkable


class Signal(TypedDict):
    """A requirement signal, normalized to a local file."""

    signal_id: str
    kind: str  # "meeting_notes" | "transcript" | "document" | "idea"
    path: str  # local path after normalization
    received_at: float


@runtime_checkable
class SignalSource(Protocol):
    """Where requirement signals come from (MVP: the filesystem inbox)."""

    def poll(self) -> list[Signal]:
        """Return pending signals. Never mutates state."""
        ...

    def ack(self, signal_id: str) -> None:
        """Mark a signal processed (move to processed/). Idempotent:
        acking an already-acked or unknown id is a silent no-op."""
        ...


@runtime_checkable
class TrackerPort(Protocol):
    """Where requirement units live (MVP: the spec file IS the ticket)."""

    def upsert(self, spec_path: str) -> str:
        """Register/validate a spec file; returns the external ref."""
        ...

    def transition(self, ref: str, status: str) -> None:
        """Move the tracked unit to a new lifecycle status. Illegal
        transitions raise; they are never coerced."""
        ...

    def comment(self, ref: str, body: str) -> None:
        """Append an audit note to the tracked unit's log."""
        ...


class BuildBrief(TypedDict):
    """What a coding agent needs to build one approved spec."""

    spec_id: str
    kind: str  # bug|enhancement|new_feature
    summary: str
    description: str  # rendered from spec body + linked ADRs
    acceptance_criteria: list[str]
    repo_path: str


class BuildResult(TypedDict):
    """Outcome of one dispatch. Operational failures are values
    (``status="failed"``/``"needs_human"``), not exceptions."""

    status: str  # completed|failed|needs_human
    pr_url: str | None
    branch: str | None
    trace_path: str  # SPEC-004 §3.1: every dispatch MUST produce a trace


@runtime_checkable
class DispatchPort(Protocol):
    """Hands approved work to a coding backend (MVP: multicoders/mock)."""

    def dispatch(self, brief: BuildBrief) -> BuildResult:
        """Run one brief to completion. Never raises for operational
        failures — those come back as ``BuildResult.status``."""
        ...

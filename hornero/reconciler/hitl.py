"""HITL gate: fail-closed terminal approval (SPEC-001 §9 step 4, G3).

No TTY, no approval channel => no approvals, no exception — everything stays
proposed and the run ends quietly (CLAUDE.md invariant 2). Confidence is
displayed to the human, never used to auto-approve (§13 R1). DUPLICATE
deltas are never presented (§6). Plain stdlib terminal — no rich/curses (NG4).
"""

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from hornero.models import DeltaKind, RequirementDelta


class Decision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    EDITED = "edited"  # approved with a human-edited patch
    SKIPPED = "skipped"


@dataclass(frozen=True)
class ReviewResult:
    decision: Decision
    patch: str | None = None  # set only for EDITED


@dataclass(frozen=True)
class ReviewedDelta:
    delta: RequirementDelta
    result: ReviewResult


@runtime_checkable
class ApprovalChannel(Protocol):
    def review(self, delta: RequirementDelta, diff_text: str) -> ReviewResult: ...


def render_delta(delta: RequirementDelta) -> str:
    lines = [
        f"[{delta.kind.value.upper()}] {delta.delta_id} — {delta.title}",
        f"  summary:    {delta.summary}",
        f"  confidence: {delta.confidence:.2f}  (informational only)",
        f"  affects:    {', '.join(delta.affected_specs) or '(new spec)'}",
        "  evidence:",
    ]
    for ev in delta.evidence:
        lines.append(f"    {ev.signal_id} @ {ev.locator}: {ev.excerpt!r}")
    return "\n".join(lines)


class TerminalChannel:
    """Interactive TTY reviewer. Construct via :meth:`open`, which refuses
    non-TTY environments by returning ``None`` — the fail-closed seam."""

    def __init__(self) -> None:
        self._in = input

    @classmethod
    def open(cls) -> "TerminalChannel | None":
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            return None
        return cls()

    def review(self, delta: RequirementDelta, diff_text: str) -> ReviewResult:
        print(render_delta(delta))
        print("  proposed patch:")
        for line in diff_text.splitlines():
            print(f"    {line}")
        while True:
            answer = self._in("[a]pprove / [r]eject / [e]dit / [s]kip > ").strip().lower()
            if answer == "a":
                return ReviewResult(Decision.APPROVED)
            if answer == "r":
                return ReviewResult(Decision.REJECTED)
            if answer == "s":
                return ReviewResult(Decision.SKIPPED)
            if answer == "e":
                edited = _edit_in_editor(diff_text)
                if edited is None or not edited.strip():
                    print("  no $EDITOR available or empty patch — rejecting "
                          "(never auto-approving).")
                    return ReviewResult(Decision.REJECTED)
                return ReviewResult(Decision.EDITED, patch=edited)
            # empty or unknown input: re-prompt, never default


def _edit_in_editor(text: str) -> str | None:
    editor = os.environ.get("EDITOR")
    if not editor:
        return None
    with tempfile.NamedTemporaryFile(
        "w+", suffix=".patch", delete=False, encoding="utf-8"
    ) as tf:
        tf.write(text)
        path = tf.name
    try:
        subprocess.run([editor, path], check=True)
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except (OSError, subprocess.CalledProcessError):
        return None
    finally:
        os.unlink(path)


def gate(
    deltas: list[RequirementDelta], channel: ApprovalChannel | None
) -> list[ReviewedDelta]:
    """Review every delta. ``channel is None`` => everything SKIPPED, no
    exception: fail-closed is a quiet outcome. DUPLICATEs never reach the
    channel (§6) — they pass through as SKIPPED."""
    reviewed: list[ReviewedDelta] = []
    for delta in deltas:
        if delta.kind is DeltaKind.DUPLICATE or channel is None:
            reviewed.append(ReviewedDelta(delta, ReviewResult(Decision.SKIPPED)))
            continue
        reviewed.append(ReviewedDelta(delta, channel.review(delta, delta.proposed_patch)))
    return reviewed

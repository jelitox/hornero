"""``hornero reconcile`` orchestration (SPEC-001 §9, §10).

poll -> retrieve+draft -> HITL -> apply, with ledger records per run.

``--dry-run`` prints deltas and stops: no HITL gate, no apply, no ack, no
spec mutation — only the (gitignored) ledger records the run. A normal run
without a TTY is fail-closed: deltas stay proposed, exit 0, no exception.

Model resolution is deliberately austere in MVP: ``models.reconciler`` set
to ``fake:<script.json>`` loads the deterministic :class:`FakeLLM`; anything
else (or nothing) refuses to run BEFORE polling. Real providers arrive
post-MVP behind the same :class:`LLMPort` seam.
"""

import json
import time
from collections.abc import Callable
from dataclasses import asdict
from datetime import date
from pathlib import Path

from hornero.adapters.inbox import InboxSource
from hornero.adapters.repo_tracker import RepoTracker
from hornero.config import ConfigError, load_config
from hornero.lifecycle import SpecCorpus
from hornero.memory.knowledge import open_knowledge
from hornero.memory.ledger import Ledger
from hornero.models import DeltaKind, Evidence, RequirementDelta
from hornero.reconciler.apply import apply_deltas
from hornero.reconciler.draft import LLMPort, draft_deltas
from hornero.ports import Signal, SignalSource
from hornero.reconciler.hitl import ApprovalChannel, Decision, TerminalChannel, gate

Echo = Callable[[str], None]





DELTA_BUDGET = 5  # SPEC-003 §7 U2: max fresh deltas surfaced per signal/run


class _AckRouter:
    """Routes acks back to the producing source. A signal id with no origin
    (revived queued delta from an earlier, already-acked run) is a no-op."""

    def __init__(self, origin: dict[str, SignalSource]) -> None:
        self._origin = origin

    def poll(self) -> list[Signal]:
        return []

    def ack(self, signal_id: str) -> None:
        src = self._origin.get(signal_id)
        if src is not None:
            src.ack(signal_id)


def _revive(row: dict) -> RequirementDelta:
    payload = json.loads(row["payload_json"])
    return RequirementDelta(
        delta_id=row["delta_id"],
        kind=DeltaKind(row["kind"]),
        title=row["title"],
        summary=payload["summary"],
        affected_specs=payload["affected_specs"],
        evidence=[Evidence(**e) for e in payload["evidence"]],
        confidence=row["confidence"],
        proposed_patch=payload["proposed_patch"],
    )


def _payload(delta: RequirementDelta) -> dict:
    data = asdict(delta)
    data.pop("delta_id", None)
    return data


def run_reconcile(
    root: Path,
    *,
    dry_run: bool = False,
    llm: LLMPort | None = None,
    channel: ApprovalChannel | None = None,
    now: float | None = None,
    today: str | None = None,
    echo: Echo = print,
) -> int:
    try:
        cfg = load_config(root)
    except ConfigError as exc:
        echo(f"config error: {exc}")
        return 1
    if llm is None:
        from hornero.llm import resolve_llm

        llm = resolve_llm(cfg, root, "reconciler")
    if llm is None:
        echo(
            "no model configured for the reconciler "
            "(set models.reconciler; MVP supports fake:<script.json>)"
        )
        return 3  # refuse before polling: no half-run

    now = time.time() if now is None else now
    today = date.today().isoformat() if today is None else today

    from hornero import layout

    ledger = Ledger(root / ".hornero" / "ledger.db")
    corpus = SpecCorpus(layout.specs_dir(root))
    knowledge = open_knowledge(root)

    # SPEC-003 §6: signal sources are config-selected; git is opt-in.
    source_names = cfg.signal_sources or [cfg.signal_source]
    origin: dict[str, SignalSource] = {}
    signals: list[Signal] = []
    for name in source_names:
        if name == "inbox":
            src: SignalSource = InboxSource(root / ".hornero")
        elif name == "git":
            from hornero.adapters.gitsource import GitSource

            src = GitSource(root)
        else:  # fail-closed: an unknown source never silently no-ops
            echo(f"unknown signal source {name!r}")
            return 1
        for sig in src.poll():
            origin[sig["signal_id"]] = src
            signals.append(sig)
    source: SignalSource = _AckRouter(origin)

    run_id = ledger.next_run_id()
    ledger.record_run(run_id, "reconcile", now, dry_run=dry_run)

    # U2 queue: deltas parked past the budget on a previous run go first.
    deltas: list[RequirementDelta] = [
        _revive(row) for row in ledger.queued_deltas()
    ]
    if deltas:
        echo(f"{len(deltas)} queued delta(s) from previous runs re-presented.")

    fresh: list[RequirementDelta] = []
    for i, sig in enumerate(signals, start=1):
        text = Path(sig["path"]).read_text(encoding="utf-8", errors="replace")
        fresh.extend(
            draft_deltas(
                sig, text, corpus, knowledge, llm, ledger, f"{run_id}.{i}", now
            )
        )

    # SPEC-003 §7 U2 delta budget: at most DELTA_BUDGET fresh deltas per
    # signal per run, highest confidence first; the excess is QUEUED in the
    # ledger (never dropped) and re-presented next run.
    by_signal: dict[str, list[RequirementDelta]] = {}
    for d in fresh:
        sid = d.evidence[0].signal_id if d.evidence else ""
        by_signal.setdefault(sid, []).append(d)
    for sid, group in sorted(by_signal.items()):
        group.sort(key=lambda d: (-d.confidence, d.delta_id))
        deltas.extend(group[:DELTA_BUDGET])
        for d in group[DELTA_BUDGET:]:
            ledger.record_delta(
                d.delta_id, run_id, d.kind.value, d.title, "queued",
                d.confidence, _payload(d),
            )
        if len(group) > DELTA_BUDGET:
            echo(
                f"delta budget: {len(group) - DELTA_BUDGET} excess delta(s) "
                f"from {sid} queued for the next run."
            )

    echo(f"{len(deltas)} delta(s) drafted (run {run_id}):")
    for d in deltas:
        affects = ", ".join(d.affected_specs) or "(new spec)"
        echo(f"  [{d.kind.value}] {d.delta_id} — {d.title} "
             f"(confidence {d.confidence:.2f}; affects {affects})")
        for ev in d.evidence:
            echo(f"      {ev.signal_id} @ {ev.locator}: {ev.excerpt!r}")

    if dry_run:
        for d in deltas:
            ledger.record_delta(
                d.delta_id, run_id, d.kind.value, d.title, "proposed",
                d.confidence, _payload(d),
            )
        ledger.finish_run(run_id, now)
        echo("dry-run: nothing applied.")
        return 0

    if channel is None:
        channel = TerminalChannel.open()
    if channel is None:  # fail-closed, quietly
        for d in deltas:
            ledger.record_delta(
                d.delta_id, run_id, d.kind.value, d.title, "proposed",
                d.confidence, _payload(d),
            )
        ledger.finish_run(run_id, now)
        echo(
            f"no approval channel (stdin/stdout is not a TTY); "
            f"{len(deltas)} delta(s) remain proposed."
        )
        return 0

    reviewed = gate(deltas, channel)
    tracker = RepoTracker(layout.specs_dir(root), clock=lambda: today)
    report = apply_deltas(
        reviewed, corpus, tracker, source,
        decisions_dir=layout.decisions_dir(root),
        proposals_dir=layout.proposals_dir(root),
        templates_dir=layout.templates_dir(root),
        today=today,
    )

    # OQ2 (resolved: yes, F4): DUPLICATE deltas leave signal-strength
    # telemetry on the covering spec's Log. Best-effort — telemetry must
    # never break reconciliation.
    for item in reviewed:
        d = item.delta
        if d.kind.value != "duplicate":
            continue
        mention = ", ".join(ev.signal_id for ev in d.evidence)
        for ref in d.affected_specs:
            try:
                tracker.comment(ref, f"mentioned again in {mention} ({d.delta_id}).")
            except Exception as exc:
                ledger.record_dropped_draft(
                    run_id, "duplicate_comment_failed",
                    {"delta_id": d.delta_id, "ref": ref, "error": str(exc)}, now,
                )

    status_by_decision = {
        Decision.APPROVED: "approved",
        Decision.EDITED: "approved",
        Decision.REJECTED: "rejected",
        Decision.SKIPPED: "proposed",
    }
    for item in reviewed:
        d = item.delta
        ledger.record_delta(
            d.delta_id, run_id, d.kind.value, d.title,
            status_by_decision[item.result.decision], d.confidence, _payload(d),
        )
    ledger.finish_run(run_id, now)

    echo(
        f"applied: {len(report.created)} created, {len(report.patched)} patched, "
        f"{len(report.obsoleted)} obsoleted, {len(report.proposals)} proposal(s), "
        f"{len(report.adrs)} ADR(s), {len(report.acked_signals)} signal(s) acked."
    )
    for delta_id, msg in report.errors:
        echo(f"  ERROR {delta_id}: {msg}")
    return 1 if report.errors else 0

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

import time
from collections.abc import Callable
from dataclasses import asdict
from datetime import date
from pathlib import Path

from hornero.adapters.inbox import InboxSource
from hornero.adapters.repo_tracker import RepoTracker
from hornero.config import ConfigError, HorneroConfig, load_config
from hornero.lifecycle import SpecCorpus
from hornero.memory.knowledge import open_knowledge
from hornero.memory.ledger import Ledger
from hornero.models import RequirementDelta
from hornero.reconciler.apply import apply_deltas
from hornero.reconciler.draft import LLMPort, draft_deltas
from hornero.reconciler.hitl import ApprovalChannel, Decision, TerminalChannel, gate
from hornero.reconciler.testing import FakeLLM

Echo = Callable[[str], None]


def _resolve_llm(cfg: HorneroConfig, root: Path) -> LLMPort | None:
    spec = cfg.models.get("reconciler", "")
    if spec.startswith("fake:"):
        path = Path(spec[len("fake:") :])
        if not path.is_absolute():
            path = root / path
        return FakeLLM.from_file(path)
    return None


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
        llm = _resolve_llm(cfg, root)
    if llm is None:
        echo(
            "no model configured for the reconciler "
            "(set models.reconciler; MVP supports fake:<script.json>)"
        )
        return 3  # refuse before polling: no half-run

    now = time.time() if now is None else now
    today = date.today().isoformat() if today is None else today

    ledger = Ledger(root / ".hornero" / "ledger.db")
    source = InboxSource(root / ".hornero")
    corpus = SpecCorpus(root / "product" / "specs")
    knowledge = open_knowledge(root)

    run_id = ledger.next_run_id()
    ledger.record_run(run_id, "reconcile", now, dry_run=dry_run)

    deltas: list[RequirementDelta] = []
    for i, sig in enumerate(source.poll(), start=1):
        text = Path(sig["path"]).read_text(encoding="utf-8", errors="replace")
        deltas.extend(
            draft_deltas(
                sig, text, corpus, knowledge, llm, ledger, f"{run_id}.{i}", now
            )
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
    tracker = RepoTracker(root / "product" / "specs", clock=lambda: today)
    report = apply_deltas(
        reviewed, corpus, tracker, source,
        root / "product" / "decisions", today,
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
        f"{len(report.obsoleted)} obsoleted, {len(report.adrs)} ADR(s), "
        f"{len(report.acked_signals)} signal(s) acked."
    )
    for delta_id, msg in report.errors:
        echo(f"  ERROR {delta_id}: {msg}")
    return 1 if report.errors else 0

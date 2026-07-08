"""``hornero build`` (SPEC-001 §10): approved specs -> briefs -> DispatchPort.

NG3 — no autonomous dispatch: with no approved specs this is a quiet no-op
(exit 0). Explicit ids that are not approved abort the WHOLE invocation
before any transition (all-or-nothing, conservative). Each spec transitions
``approved -> building`` before dispatch and ``-> review`` / ``needs_human``
after, through the tracker, so a crash mid-dispatch leaves an honest
``building`` visible in ``hornero status``.
"""

import time
from collections.abc import Callable
from datetime import date
from pathlib import Path

from hornero.adapters.dispatch import MulticodersDispatch, brief_from_spec
from hornero.adapters.repo_tracker import RepoTracker
from hornero.config import ConfigError, load_config
from hornero.lifecycle import SpecCorpus, Status
from hornero.memory.ledger import Ledger

Echo = Callable[[str], None]

def _regenerate_reports(root: Path, echo: Echo) -> None:
    """Final step of a successful build (§11): the change-set ships code +
    spec + refreshed reports atomically."""
    from hornero.reports.run import run_report

    run_report(root, echo=echo)


# Extensible seam; report regeneration is the F5 default.
post_build_hooks: list[Callable[[Path, Echo], None]] = [_regenerate_reports]


def run_build(
    root: Path,
    spec_ids: list[str],
    *,
    backend: str | None = None,
    now: float | None = None,
    today: str | None = None,
    echo: Echo = print,
) -> int:
    try:
        cfg = load_config(root)
    except ConfigError as exc:
        echo(f"config error: {exc}")
        return 1
    now = time.time() if now is None else now
    today = date.today().isoformat() if today is None else today

    from hornero import layout

    corpus = SpecCorpus(layout.specs_dir(root))
    approved = [d.spec_id for d in corpus.docs if d.status is Status.APPROVED]

    if spec_ids:
        missing = [s for s in spec_ids if s not in corpus.by_id]
        not_approved = [
            s for s in spec_ids if s in corpus.by_id and s not in approved
        ]
        if missing or not_approved:  # all-or-nothing: dispatch NOTHING
            for s in missing:
                echo(f"unknown spec: {s}")
            for s in not_approved:
                echo(
                    f"not approved: {s} "
                    f"(status: {corpus.by_id[s].status.value})"
                )
            return 1
        targets = list(spec_ids)
    else:
        targets = approved

    if not targets:
        echo("nothing to build (no approved specs).")  # NG3: quiet no-op
        return 0

    backend_order = [backend] if backend else cfg.dispatch.backend_order
    dispatcher = MulticodersDispatch(backend_order, root)
    tracker = RepoTracker(layout.specs_dir(root), clock=lambda: today)
    ledger = Ledger(root / ".hornero" / "ledger.db")
    run_id = ledger.next_run_id()
    ledger.record_run(run_id, "build", now)

    failures = 0
    for spec_id in targets:
        doc = corpus.by_id[spec_id]
        tracker.transition(spec_id, "building")
        tracker.comment(spec_id, f"build started (run {run_id}, backend "
                                 f"{dispatcher.backend_name}).")
        brief = brief_from_spec(
            doc, str(root), cfg.criterion_allowlist, layout.decisions_dir(root)
        )
        result = dispatcher.dispatch(brief)
        ledger.record_dispatch(
            spec_id, run_id, result["status"], result["pr_url"],
            result["branch"], result["log_path"], now,
        )
        if result["status"] == "completed":
            tracker.transition(spec_id, "review")
            tracker.comment(spec_id, f"PR opened: {result['pr_url']}")
            echo(f"{spec_id}: completed -> review ({result['pr_url']})")
        else:
            failures += 1
            tracker.transition(spec_id, "needs_human")
            tracker.comment(
                spec_id,
                f"dispatch {result['status']}; see log {result['log_path']}",
            )
            echo(f"{spec_id}: {result['status']} -> needs_human "
                 f"(log: {result['log_path']})")

    ledger.finish_run(run_id, now)
    if failures == 0:
        for hook in post_build_hooks:
            hook(root, echo)
    return 0 if failures == 0 else 1

"""``hornero report [--only <name>]`` + the post-build regeneration hook."""

from collections.abc import Callable
from pathlib import Path

from hornero.reports import capabilities, traceability, workflows
from hornero.reports.engine import ReportContext, build_context, write_report

GENERATORS: dict[str, Callable[[ReportContext], str]] = {
    "capabilities": capabilities.generate,
    "workflows": workflows.generate,
    "traceability": traceability.generate,
}

Echo = Callable[[str], None]


def run_report(
    root: Path,
    only: str | None = None,
    echo: Echo = print,
    now_iso: str | None = None,
) -> int:
    if only is not None and only not in GENERATORS:
        echo(f"unknown report {only!r}; choose from {sorted(GENERATORS)}")
        return 1
    from hornero import layout, watermarks

    before = watermarks.content_snapshot([layout.reports_dir(root)])
    ctx = build_context(root)
    try:
        for name in [only] if only else sorted(GENERATORS):
            path = write_report(root, f"{name}.html", GENERATORS[name](ctx))
            echo(f"wrote {path}")
    finally:
        ctx.ledger.close()

    # SPEC-003 §5 no-op discipline: identical bytes => no watermark write.
    after = watermarks.content_snapshot([layout.reports_dir(root)])
    if after == before:
        echo("reports already current")
        return 0
    from datetime import datetime, timezone

    watermarks.update(root, "reports", {
        "git_head": watermarks.git_head(root),
        "updated_at": now_iso or datetime.now(timezone.utc).isoformat(),
        "content_hash": after,
    })
    return 0

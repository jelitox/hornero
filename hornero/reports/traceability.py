"""``traceability.html``: signal → delta → spec → PR → merge per requirement
(SPEC-001 §11 — the audit view, read straight out of the ledger + frontmatter).

Missing stages render as explicit gaps: showing what has NOT happened is the
point of an audit view. Nothing is inferred, let alone invented.
"""

import json
from pathlib import Path

from hornero.lifecycle import Status
from hornero.reports.engine import ReportContext, esc, render_page, spec_href

_GAP = '<span class="gap">—</span>'


def _sdd_tasks_by_spec(ctx: ReportContext) -> dict[str, set[str]]:
    """SPEC-002 §8: map spec key -> SDD task ids from sdd/tasks/index/*.json.

    A task belongs to a spec when its ``feature_id`` equals the spec id OR
    its ``spec`` field references the spec's file; keys carry both forms so
    ``generate`` can look up by id or by filename.
    """
    out: dict[str, set[str]] = {}
    if not ctx.tasks_index_dir.is_dir():
        return out
    for path in sorted(ctx.tasks_index_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue  # a broken index never breaks the audit view
        for task in data.get("tasks", []):
            task_id = task.get("id")
            if not task_id:
                continue
            if task.get("feature_id"):
                out.setdefault(task["feature_id"], set()).add(task_id)
            if task.get("spec"):
                out.setdefault(Path(task["spec"]).name, set()).add(task_id)
    return out


def generate(ctx: ReportContext) -> str:
    docs = sorted(ctx.corpus.docs, key=lambda d: d.spec_id)
    tasks_by_spec = _sdd_tasks_by_spec(ctx)
    rows: list[str] = []
    for doc in docs:
        chain = ctx.ledger.trace(doc.spec_id)

        signals = list(doc.sources)
        for delta_row in chain["deltas"]:
            payload = json.loads(delta_row["payload_json"])
            for ev in payload.get("evidence", []):
                sid = ev.get("signal_id")
                if sid and sid not in signals:
                    signals.append(sid)

        deltas = ", ".join(
            esc(d["delta_id"])
            + (f" ({esc(d['outcome'])})" if d.get("outcome") else "")
            for d in chain["deltas"]
        ) or _GAP
        task_ids = tasks_by_spec.get(doc.spec_id, set()) | tasks_by_spec.get(
            doc.path.name, set()
        )
        tasks_cell = ", ".join(esc(t) for t in sorted(task_ids)) or _GAP
        runs = ctx.ledger.agent_runs(doc.spec_id)  # SPEC-004 §3.3: process
        runs_cell = ", ".join(esc(r["run_ref"]) for r in runs) or _GAP
        prs = [d["pr_url"] for d in chain["dispatches"] if d["pr_url"]]
        pr_cell = ", ".join(esc(u) for u in prs) or _GAP
        merged = "yes" if doc.status is Status.DONE else _GAP

        rows.append(
            "<tr>"
            f"<td>{', '.join(esc(s) for s in signals) or _GAP}</td>"
            f"<td>{deltas}</td>"
            f'<td><a href="{esc(spec_href(doc.path))}">{esc(doc.spec_id)}</a> '
            f"<small>({esc(doc.status.value)})</small></td>"
            f"<td>{tasks_cell}</td>"
            f"<td>{runs_cell}</td>"
            f"<td>{pr_cell}</td>"
            f"<td>{merged}</td>"
            "</tr>"
        )
    body = (
        "<p>The audit chain per requirement. Gaps (—) are honest: they mark "
        "stages that have not happened.</p>"
        "<table><tr><th>Signals</th><th>Deltas</th><th>Spec</th>"
        "<th>SDD tasks</th><th>Runs</th><th>PR</th><th>Merged</th></tr>"
        + "".join(rows) + "</table>"
        if rows
        else "<p class='gap'>No specs yet.</p>"
    )
    return render_page("Traceability", body, ctx.head_ref)

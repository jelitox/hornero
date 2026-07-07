"""``traceability.html``: signal → delta → spec → PR → merge per requirement
(SPEC-001 §11 — the audit view, read straight out of the ledger + frontmatter).

Missing stages render as explicit gaps: showing what has NOT happened is the
point of an audit view. Nothing is inferred, let alone invented.
"""

import json

from hornero.lifecycle import Status
from hornero.reports.engine import ReportContext, esc, render_page, spec_href

_GAP = '<span class="gap">—</span>'


def generate(ctx: ReportContext) -> str:
    docs = sorted(ctx.corpus.docs, key=lambda d: d.spec_id)
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

        deltas = ", ".join(esc(d["delta_id"]) for d in chain["deltas"]) or _GAP
        prs = [d["pr_url"] for d in chain["dispatches"] if d["pr_url"]]
        pr_cell = ", ".join(esc(u) for u in prs) or _GAP
        merged = "yes" if doc.status is Status.DONE else _GAP

        rows.append(
            "<tr>"
            f"<td>{', '.join(esc(s) for s in signals) or _GAP}</td>"
            f"<td>{deltas}</td>"
            f'<td><a href="{esc(spec_href(doc.path))}">{esc(doc.spec_id)}</a> '
            f"<small>({esc(doc.status.value)})</small></td>"
            f"<td>{pr_cell}</td>"
            f"<td>{merged}</td>"
            "</tr>"
        )
    body = (
        "<p>The audit chain per requirement. Gaps (—) are honest: they mark "
        "stages that have not happened.</p>"
        "<table><tr><th>Signals</th><th>Deltas</th><th>Spec</th><th>PR</th>"
        "<th>Merged</th></tr>" + "".join(rows) + "</table>"
        if rows
        else "<p class='gap'>No specs yet.</p>"
    )
    return render_page("Traceability", body, ctx.head_ref)

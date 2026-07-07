"""``workflows.html``: flows extracted from the graph (SPEC-001 §11).

Without GraphIndex (the tested reality) edges are derived structurally —
spec→component from ``src/`` mentions, spec→decision from ADR references,
spec→spec from ``supersedes:`` — and rendered in two views: business
(outcome-centric) and technical (component-centric). Static HTML only.
"""

import re

from hornero.lifecycle import SpecDoc, Status
from hornero.reports.capabilities import component_of
from hornero.reports.engine import ReportContext, esc, render_page, spec_href

_ADR_REF = re.compile(r"\bADR-\d{3}\b")

_BUSINESS_BUCKETS: list[tuple[str, set[Status]]] = [
    ("Shipped", {Status.DONE}),
    ("In flight", {Status.BUILDING, Status.REVIEW}),
    ("Committed", {Status.APPROVED}),
    ("Under consideration", {Status.PROPOSED, Status.NEEDS_HUMAN}),
    ("Discarded", {Status.REJECTED, Status.OBSOLETE}),
]


def _decisions_of(doc: SpecDoc) -> list[str]:
    return sorted(set(_ADR_REF.findall(doc.body)))


def generate(ctx: ReportContext) -> str:
    docs = sorted(ctx.corpus.docs, key=lambda d: d.spec_id)
    parts: list[str] = []

    parts.append("<h2>Business view</h2>")
    for label, statuses in _BUSINESS_BUCKETS:
        group = [d for d in docs if d.status in statuses]
        if not group:
            continue
        items = "".join(
            f'<li><a href="{esc(spec_href(d.path))}">{esc(d.spec_id)}</a> — '
            f"{esc(d.title)}"
            + (
                f" <small>(supersedes {esc(', '.join(d.supersedes))})</small>"
                if d.supersedes else ""
            )
            + "</li>"
            for d in group
        )
        parts.append(f"<h3>{esc(label)}</h3><ul>{items}</ul>")

    parts.append("<h2>Technical view</h2>")
    by_component: dict[str, list[SpecDoc]] = {}
    for doc in docs:
        by_component.setdefault(component_of(doc), []).append(doc)
    for component in sorted(by_component):
        rows = "".join(
            "<tr>"
            f'<td><a href="{esc(spec_href(d.path))}">{esc(d.spec_id)}</a></td>'
            f"<td>{esc(d.title)}</td>"
            f"<td>{esc(d.status.value)}</td>"
            f"<td>{', '.join(esc(a) for a in _decisions_of(d)) or '<span class=gap>—</span>'}</td>"
            "</tr>"
            for d in by_component[component]
        )
        parts.append(
            f"<h3><code>{esc(component)}</code></h3>"
            "<table><tr><th>Spec</th><th>Flow</th><th>Status</th>"
            f"<th>Decisions</th></tr>{rows}</table>"
        )
    if not docs:
        parts.append("<p class='gap'>No specs yet.</p>")
    return render_page("Workflows", "\n".join(parts), ctx.head_ref)

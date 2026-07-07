"""``capabilities.html``: what the product does today (SPEC-001 §11).

Specs grouped by component; each capability links to its spec file and its
originating signals. Component attribution is a structural heuristic: the
first ``src/<segment>`` path mentioned in the spec body, else "general" —
no model in the loop (G5).
"""

import re

from hornero.lifecycle import SpecDoc, Status
from hornero.reports.engine import ReportContext, esc, render_page, spec_href

_SRC_SEG = re.compile(r"\bsrc/([A-Za-z0-9_-]+)")

_STATUS_ORDER = [
    Status.DONE, Status.REVIEW, Status.BUILDING, Status.APPROVED,
    Status.PROPOSED, Status.NEEDS_HUMAN, Status.REJECTED, Status.OBSOLETE,
]


def component_of(doc: SpecDoc) -> str:
    m = _SRC_SEG.search(doc.body)
    return m.group(1) if m else "general"


def _row(doc: SpecDoc) -> str:
    sources = ", ".join(esc(s) for s in doc.sources) or '<span class="gap">—</span>'
    return (
        "<tr>"
        f'<td><a href="{esc(spec_href(doc.path))}">{esc(doc.spec_id)}</a></td>'
        f"<td>{esc(doc.title)}</td>"
        f'<td><span class="status status-{esc(doc.status.value)}">'
        f"{esc(doc.status.value)}</span></td>"
        f"<td>{sources}</td>"
        "</tr>"
    )


def generate(ctx: ReportContext) -> str:
    docs = sorted(ctx.corpus.docs, key=lambda d: d.spec_id)
    by_component: dict[str, list[SpecDoc]] = {}
    for doc in docs:
        by_component.setdefault(component_of(doc), []).append(doc)

    parts: list[str] = []
    done_total = sum(1 for d in docs if d.status is Status.DONE)
    parts.append(
        f"<p>{len(docs)} spec(s) tracked; <strong>{done_total} shipped</strong>.</p>"
    )
    for component in sorted(by_component):
        group = by_component[component]
        group.sort(key=lambda d: (_STATUS_ORDER.index(d.status), d.spec_id))
        parts.append(f"<h2>{esc(component)}</h2>")
        parts.append(
            "<table><tr><th>Spec</th><th>Capability</th><th>Status</th>"
            "<th>Originating signals</th></tr>"
            + "".join(_row(d) for d in group)
            + "</table>"
        )
    if not docs:
        parts.append("<p class='gap'>No specs yet — drop a signal in the inbox.</p>")
    return render_page("Capabilities", "\n".join(parts), ctx.head_ref)

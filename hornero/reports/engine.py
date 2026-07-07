"""Shared report engine (SPEC-001 §11, G5).

Reports read ONLY the knowledge layer, spec frontmatter/bodies, decisions,
and the ledger — never parametric memory. That rule is enforced by
construction: :class:`ReportContext` is the whole data surface and no LLM
port exists anywhere in report code. Output is self-contained static HTML:
inline CSS, zero scripts, zero external assets. Deterministic: stable
ordering, no generation timestamps — provenance is the knowledge manifest's
``head_ref``.
"""

import html
import json
from dataclasses import dataclass
from pathlib import Path

from hornero.lifecycle import SpecCorpus
from hornero.memory.knowledge import KnowledgeLayer, open_knowledge
from hornero.memory.ledger import Ledger

_CSS = """\
body { font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 60rem;
       padding: 0 1rem; color: #1a1a1a; background: #fff; line-height: 1.5; }
h1 { border-bottom: 2px solid #b45309; padding-bottom: .3rem; }
h2 { margin-top: 2rem; color: #7c2d12; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
th, td { border: 1px solid #d4d4d4; padding: .4rem .6rem; text-align: left;
         vertical-align: top; }
th { background: #fef3c7; }
code { background: #f5f5f5; padding: .1rem .3rem; border-radius: 3px; }
.status { font-size: .85em; padding: .1rem .5rem; border-radius: 999px;
          background: #e5e5e5; }
.status-done { background: #bbf7d0; }
.status-obsolete, .status-rejected { background: #fecaca; }
.gap { color: #a3a3a3; }
footer { margin-top: 3rem; font-size: .8em; color: #737373;
         border-top: 1px solid #e5e5e5; padding-top: .5rem; }
"""


def esc(text: str) -> str:
    return html.escape(str(text), quote=True)


@dataclass
class ReportContext:
    """The ONLY data sources a generator may touch (G5)."""

    corpus: SpecCorpus
    knowledge: KnowledgeLayer
    ledger: Ledger
    decisions_dir: Path
    head_ref: str | None


def build_context(root: Path) -> ReportContext:
    head_ref = None
    manifest = root / ".hornero" / "knowledge" / "manifest.json"
    if manifest.is_file():
        head_ref = json.loads(manifest.read_text(encoding="utf-8")).get("head_ref")
    return ReportContext(
        corpus=SpecCorpus(root / "product" / "specs"),
        knowledge=open_knowledge(root),
        ledger=Ledger(root / ".hornero" / "ledger.db"),
        decisions_dir=root / "product" / "decisions",
        head_ref=head_ref,
    )


def render_page(title: str, body_html: str, head_ref: str | None) -> str:
    provenance = (
        f"generated from repo state {esc(head_ref)}" if head_ref
        else "generated from working-tree state (no index manifest)"
    )
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        f"<title>{esc(title)}</title>\n"
        f"<style>\n{_CSS}</style>\n</head>\n<body>\n"
        f"<h1>{esc(title)}</h1>\n"
        f"{body_html}\n"
        f"<footer>hornero · {provenance} · sources: spec frontmatter, "
        "knowledge layer, ledger — never parametric memory</footer>\n"
        "</body>\n</html>\n"
    )


def spec_href(doc_path: Path) -> str:
    """Relative link that resolves from ``product/reports/``."""
    return f"../specs/{doc_path.name}"


def write_report(root: Path, name: str, html_text: str) -> Path:
    reports_dir = root / "product" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    out = reports_dir / name
    out.write_text(html_text, encoding="utf-8")
    return out

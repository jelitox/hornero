"""Root instruction-file injection (SPEC-003 §8).

``hornero init`` and ``hornero sdd install`` ensure the repo's top-level
``CLAUDE.md``/``AGENTS.md`` carry a standardized ``## Hornero`` section so
any agent entering the repo finds the wiki and the SDD workflow first.
Idempotent by contract: refreshing a current file leaves ``git diff`` empty;
the section is replaced only when missing or SEMANTICALLY stale (whitespace
never counts), and all surrounding content is preserved.
"""

import re
from pathlib import Path

SECTION_HEADER = "## Hornero"

SECTION = """\
## Hornero

This repository is managed by Hornero (product loop + SDD).

Start here:
- [Wiki quickstart](wiki/quickstart.md)
- [SDD workflow](sdd/WORKFLOW.md)
- Specs live in sdd/specs/; requirement signals go in .hornero/inbox/

When working in this repository, read the wiki quickstart first, then the
relevant spec, before exploring source.
"""

_NEXT_SECTION = re.compile(r"^## ", re.MULTILINE)


def _semantic(text: str) -> list[str]:
    return [" ".join(line.split()) for line in text.splitlines() if line.strip()]


def _extract(content: str) -> tuple[int, int] | None:
    """(start, end) offsets of the existing Hornero section, or None."""
    start = content.find(SECTION_HEADER)
    if start == -1:
        return None
    rest = content[start + len(SECTION_HEADER):]
    nxt = _NEXT_SECTION.search(rest)
    end = start + len(SECTION_HEADER) + (nxt.start() if nxt else len(rest))
    return start, end


def _inject_file(path: Path) -> bool:
    """Ensure the section in one file. Returns True when bytes changed."""
    content = path.read_text(encoding="utf-8") if path.is_file() else ""
    span = _extract(content)
    if span is None:
        sep = "" if not content else ("\n" if content.endswith("\n") else "\n\n")
        new = content + sep + SECTION
    else:
        start, end = span
        current = content[start:end]
        if _semantic(current) == _semantic(SECTION):
            return False  # semantically current: never touch formatting
        new = content[:start] + SECTION + content[end:]
    path.write_text(new, encoding="utf-8")
    return True


def inject(root: Path) -> list[str]:
    """SPEC-003 §8: top-level files only; create AGENTS.md with just the
    section when neither exists. Returns the files that changed."""
    targets = [p for p in (root / "CLAUDE.md", root / "AGENTS.md") if p.is_file()]
    if not targets:
        targets = [root / "AGENTS.md"]
    return [p.name for p in targets if _inject_file(p)]

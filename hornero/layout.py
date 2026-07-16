"""Repo layout (SPEC-001 §4 as amended by SPEC-002 §2).

Hornero's native spec store IS the SDD layout: specs in ``sdd/specs/``,
ADRs in ``sdd/decisions/``, generated reports in ``sdd/reports/``,
low-confidence proposals in ``sdd/proposals/``. ``product/`` no longer
exists. Every consumer resolves paths through here.
"""

from pathlib import Path

SDD_STATE_DIRS = [
    "sdd/proposals", "sdd/specs", "sdd/state",
    "sdd/tasks/active", "sdd/tasks/completed", "sdd/tasks/index",
    "sdd/reviews", "sdd/decisions", "sdd/reports", "sdd/findings",
    "sdd/improvements",
]


def specs_dir(root: Path) -> Path:
    return root / "sdd" / "specs"


def decisions_dir(root: Path) -> Path:
    return root / "sdd" / "decisions"


def reports_dir(root: Path) -> Path:
    return root / "sdd" / "reports"


def proposals_dir(root: Path) -> Path:
    return root / "sdd" / "proposals"


def templates_dir(root: Path) -> Path:
    return root / "sdd" / "templates"


def tasks_index_dir(root: Path) -> Path:
    return root / "sdd" / "tasks" / "index"


def findings_dir(root: Path) -> Path:
    return root / "sdd" / "findings"


def improvements_dir(root: Path) -> Path:
    return root / "sdd" / "improvements"

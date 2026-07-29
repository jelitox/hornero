"""Universal architecture knowledge and reuse governance (SPEC-013)."""

from hornero.architecture.corpus import ArchitectureCorpus, architecture_root
from hornero.architecture.governance import (
    architecture_diff,
    build_context,
    check_architecture,
    preflight_spec,
)
from hornero.architecture.model import (
    ArchitectureError,
    ArchitectureFinding,
    ArchitectureReport,
    Resolution,
)

__all__ = [
    "ArchitectureCorpus",
    "ArchitectureError",
    "ArchitectureFinding",
    "ArchitectureReport",
    "Resolution",
    "architecture_diff",
    "architecture_root",
    "build_context",
    "check_architecture",
    "preflight_spec",
]

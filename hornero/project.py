"""Project-root discovery for commands invoked from nested directories."""

import json
from pathlib import Path


class ProjectRootError(RuntimeError):
    pass


def discover_root(start: Path) -> Path:
    """Return a verified Hornero root or a git root at the current directory."""
    current = start.resolve()
    for candidate in (current, *current.parents):
        marker = candidate / ".hornero" / "project.json"
        if candidate == current and (
            (candidate / ".hornero").is_dir() or (candidate / ".git").exists()
        ):
            return candidate
        if marker.is_file():
            try:
                identity = json.loads(marker.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if identity.get("root") == str(candidate.resolve()):
                return candidate
    raise ProjectRootError(
        f"no Hornero or git project found from {start}; run 'hornero init' "
        "from the repository root"
    )


def init_root(start: Path) -> Path:
    """Initialization is explicit: it always targets the current directory."""
    return start.resolve()

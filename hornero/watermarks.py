"""Git watermarks + content-snapshot no-op discipline (SPEC-003 §4-§5).

``.hornero/watermarks.json`` is COMMITTED (knowledge state, not operational
state): one entry per maintained surface (``wiki``, ``reports``, ``reindex``,
``gitsource``) recording the git HEAD the surface was last synced to, when,
and a hash of the produced content. A watermark is written **only after** the
snapshot check confirms content actually changed — that is what makes
scheduled loops churn-free: a quiet repo costs one hash comparison.
"""

import hashlib
import json
import subprocess
from pathlib import Path

WATERMARKS_NAME = "watermarks.json"


def _path(root: Path) -> Path:
    return root / ".hornero" / WATERMARKS_NAME


def load(root: Path) -> dict[str, dict[str, object]]:
    path = _path(root)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}  # invalid watermark => full-run semantics, never a crash
    return data if isinstance(data, dict) else {}


def get(root: Path, surface: str) -> dict[str, object] | None:
    entry = load(root).get(surface)
    return entry if isinstance(entry, dict) else None


def update(root: Path, surface: str, entry: dict[str, object]) -> None:
    data = load(root)
    data[surface] = entry
    path = _path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def git_head(root: Path) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root, capture_output=True, text=True, check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return proc.stdout.strip()


def content_snapshot(paths: list[Path], exclude: frozenset[str] = frozenset()) -> str:
    """SHA-256 over the sorted (relative-path, bytes) stream of every file
    under ``paths`` — the no-op detector. ``exclude`` names metadata files
    (e.g. a manifest embedding the git HEAD) whose churn is not content."""
    digest = hashlib.sha256()
    entries: list[tuple[str, Path]] = []
    for base in paths:
        if base.is_file():
            entries.append((base.name, base))
        elif base.is_dir():
            entries.extend(
                (p.relative_to(base).as_posix(), p)
                for p in base.rglob("*")
                if p.is_file() and p.name not in exclude
            )
    for rel, p in sorted(entries):
        digest.update(rel.encode())
        digest.update(b"\x00")
        digest.update(p.read_bytes())
        digest.update(b"\x00")
    return digest.hexdigest()

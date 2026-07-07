"""Toolkit manifest (SPEC-002 §4).

The upstream repo owns the managed set via ``sdd-toolkit.manifest.json``.
When absent (bootstrap period — ai-parrot carries none yet) Hornero falls
back to built-in patterns mirroring SPEC-002 §1.1 and the caller warns
(R6: the manifest must live upstream, versioned with the files it
describes; the fallback is a bridge, not the contract).
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

MANIFEST_NAME = "sdd-toolkit.manifest.json"


class ManifestError(ValueError):
    """Malformed manifest — fail-closed, never guess a managed set."""


@dataclass(frozen=True)
class Manifest:
    name: str
    version: str
    managed: list[str] = field(default_factory=list)
    scaffold: list[str] = field(default_factory=list)


FALLBACK_MANIFEST = Manifest(
    name="sdd-toolkit",
    version="builtin-fallback",
    managed=[
        ".claude/agents/*.md",
        ".claude/commands/*.md",
        ".claude/rules/*.md",
        ".claude/skills/meta-prompting/**/SKILL.md",
        ".claude/workflows/sdd-insight.js",
        "sdd/WORKFLOW.md",
        "sdd/templates/*.md",
    ],
    scaffold=[
        "sdd/proposals/", "sdd/specs/", "sdd/state/",
        "sdd/tasks/active/", "sdd/tasks/completed/", "sdd/tasks/index/",
        "sdd/reviews/", "sdd/decisions/", "sdd/reports/",
    ],
)


def load_manifest(upstream_root: Path) -> tuple[Manifest, bool]:
    """Load the upstream manifest; ``(FALLBACK_MANIFEST, True)`` when the
    file is absent. Malformed content raises :class:`ManifestError`."""
    path = upstream_root / MANIFEST_NAME
    if not path.is_file():
        return FALLBACK_MANIFEST, True
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ManifestError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ManifestError(f"{path}: manifest must be an object")
    for key in ("name", "version", "managed"):
        if key not in data:
            raise ManifestError(f"{path}: missing required key '{key}'")
    if not isinstance(data["managed"], list):
        raise ManifestError(f"{path}: 'managed' must be a list")
    return (
        Manifest(
            name=str(data["name"]),
            version=str(data["version"]),
            managed=[str(p) for p in data["managed"]],
            scaffold=[str(p) for p in data.get("scaffold", [])],
        ),
        False,
    )


def resolve_managed(upstream_root: Path, manifest: Manifest) -> list[str]:
    """Expand the managed glob patterns against the upstream tree into
    sorted relative POSIX paths. Patterns with no matches contribute
    nothing (a lean upstream is not an error)."""
    matches: set[str] = set()
    for pattern in manifest.managed:
        for path in upstream_root.glob(pattern):
            if path.is_file():
                matches.add(path.relative_to(upstream_root).as_posix())
    return sorted(matches)

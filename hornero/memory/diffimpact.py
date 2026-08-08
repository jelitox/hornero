"""Map a working-tree diff to structural nodes and governed SDD artifacts."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from hornero.memory import codegraph, intelligence, structural

OVERLAY_PATH = Path(".hornero") / "cache" / "diff-overlay.json"


class DiffImpactError(RuntimeError):
    pass


def changed_paths(root: Path, *, base: str = "HEAD") -> list[str]:
    try:
        diff = subprocess.run(
            ["git", "-C", str(root), "diff", "--name-only", "-z", base, "--"],
            check=True, capture_output=True, timeout=30,
        )
        untracked = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--others", "--exclude-standard", "-z"],
            check=True, capture_output=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise DiffImpactError(f"cannot inspect git diff from {base!r}: {exc}") from exc
    values = [
        item for item in (diff.stdout + untracked.stdout).decode("utf-8", "replace").split("\0")
        if item
    ]
    return sorted(set(values))


def analyze(
    root: Path, *, base: str = "HEAD", max_depth: int = 4,
    max_nodes: int = 120, write_overlay: bool = False,
) -> dict[str, Any]:
    if not codegraph.db_path(root).is_file():
        raise DiffImpactError("knowledge graph is absent; run 'hornero reindex'")
    changed = changed_paths(root, base=base)
    paths: list[dict[str, Any]] = []
    affected: dict[str, dict[str, Any]] = {}
    unindexed: list[str] = []
    for rel in changed:
        entity_id = f"file:{rel}"
        if codegraph.get_entity(root, entity_id) is None:
            unindexed.append(rel)
            continue
        result = intelligence.impact(
            root, entity_id, max_depth=max_depth, max_nodes=max_nodes
        )
        record = {"path": rel, "entity_id": entity_id, "impact": result["paths"]}
        paths.append(record)
        for item in result["paths"]:
            kind = str(item.get("kind", "unknown"))
            if kind in {
                "requirement", "criterion", "decision", "task", "test_file",
                "control", "architecture_delta", "component", "symbol",
            }:
                affected[str(item["entity_id"])] = {
                    "entity_id": str(item["entity_id"]), "kind": kind,
                    "title": str(item.get("title", "")),
                    "summary": str(item.get("summary", "")),
                    "depth": int(item["depth"]), "via": str(item["via"]),
                    "changed_from": rel,
                }
    index = structural.load_index(root) or {}
    changed_set = set(changed)
    symbols = sorted(
        str(symbol["id"])
        for item in index.get("files", [])
        if isinstance(item, dict) and item.get("path") in changed_set
        for symbol in item.get("symbols", [])
        if isinstance(symbol, dict) and symbol.get("id")
    )
    affected_requirements = {
        key for key, value in affected.items() if value["kind"] == "requirement"
    }
    contradictions = [
        item.__dict__ for item in intelligence.contradictions(root)
        if item.left in affected_requirements or item.right in affected_requirements
    ]
    payload = {
        "schema": 1, "base": base, "changed": changed,
        "changed_symbols": symbols, "paths": paths,
        "affected": [affected[key] for key in sorted(affected)],
        "contradictions": contradictions, "unindexed": unindexed,
    }
    if write_overlay:
        destination = root / OVERLAY_PATH
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return payload

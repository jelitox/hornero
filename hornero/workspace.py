"""Federated, file-based workspace graph across Hornero repositories."""

from __future__ import annotations

import json
import sqlite3
from collections import deque
from pathlib import Path
from typing import Any

from hornero.memory import codegraph


class WorkspaceError(RuntimeError):
    pass


def repositories(workspace: Path) -> list[Path]:
    workspace = workspace.resolve()
    return sorted(
        path for path in workspace.iterdir()
        if path.is_dir() and (path / ".hornero" / "project.json").is_file()
    )


def build(workspace: Path) -> dict[str, Any]:
    repos = repositories(workspace)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    for repo in repos:
        db = codegraph.db_path(repo)
        if not db.is_file():
            continue
        try:
            conn = sqlite3.connect(db)
            conn.row_factory = sqlite3.Row
            entities = conn.execute(
                "SELECT entity_id, kind, title FROM entities ORDER BY entity_id"
            ).fetchall()
            relations = conn.execute(
                "SELECT src, dst, rel FROM relations ORDER BY relation_id"
            ).fetchall()
        except sqlite3.DatabaseError as exc:
            raise WorkspaceError(f"invalid graph in {repo.name}: {exc}") from exc
        finally:
            if "conn" in locals():
                conn.close()
        nodes.extend({
            "id": f"{repo.name}/{row['entity_id']}", "repository": repo.name,
            "entity_id": row["entity_id"], "kind": row["kind"],
            "title": row["title"],
        } for row in entities)
        edges.extend({
            "src": f"{repo.name}/{row['src']}",
            "dst": f"{repo.name}/{row['dst']}", "rel": row["rel"],
        } for row in relations)
        dependencies = repo / ".hornero" / "service-dependencies.json"
        if dependencies.is_file():
            try:
                data = json.loads(dependencies.read_text(encoding="utf-8"))
                for item in data.get("dependencies", []):
                    edges.append({
                        "src": f"{repo.name}/service:{repo.name}",
                        "dst": f"{item['repository']}/service:{item.get('service', item['repository'])}",
                        "rel": "depends_on_service",
                    })
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                raise WorkspaceError(f"invalid dependencies in {repo.name}: {exc}") from exc
    payload = {
        "schema": 1, "repositories": [repo.name for repo in repos],
        "nodes": sorted(nodes, key=lambda item: item["id"]),
        "edges": sorted(edges, key=lambda item: (item["src"], item["dst"], item["rel"])),
    }
    output = workspace / ".hornero-workspace" / "graph.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def plan(workspace: Path, target: str, *, max_nodes: int = 200) -> dict[str, Any]:
    graph = build(workspace)
    adjacency: dict[str, set[str]] = {}
    for edge in graph["edges"]:
        adjacency.setdefault(edge["src"], set()).add(edge["dst"])
        adjacency.setdefault(edge["dst"], set()).add(edge["src"])
    if target not in {node["id"] for node in graph["nodes"]} and target not in adjacency:
        raise WorkspaceError(f"workspace target not found: {target}")
    queue = deque([target])
    seen = {target}
    while queue and len(seen) < max_nodes:
        for neighbor in sorted(adjacency.get(queue.popleft(), set())):
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append(neighbor)
    repos = sorted({item.split("/", 1)[0] for item in seen})
    return {"target": target, "affected_nodes": sorted(seen), "repositories": repos}

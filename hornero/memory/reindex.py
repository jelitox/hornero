"""``hornero reindex``: the ONLY writer of ``.hornero/knowledge/`` (SPEC-001 §8).

Rebuilds deterministically from ``sdd/`` + ``.hornero/processed/``:
same repo state => byte-identical artifacts (sorted inputs, sorted JSON
keys, no wall-clock in outputs — provenance is the git ``head_ref``). The
manifest records source content hashes (feeding ``hornero status``
staleness, §13 R3) plus model/prompt hashes (null in fallback mode, which
needs no model at all).
"""

import hashlib
import json
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

from hornero.memory.knowledge import (
    TokenOverlapKnowledge,
    available,
    knowledge_roots,
)
from hornero.memory import codegraph

MANIFEST_NAME = "manifest.json"
FALLBACK_INDEX = "fallback/index.json"


def _valid_json(path: Path) -> bool:
    try:
        json.loads(path.read_text(encoding="utf-8"))
        return True
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return False


def _valid_graph(path: Path) -> bool:
    try:
        conn = sqlite3.connect(path)
        try:
            quick = conn.execute("PRAGMA quick_check").fetchone()
            meta = conn.execute(
                "SELECT value FROM meta WHERE key = 'schema'"
            ).fetchone()
            return bool(quick and quick[0] == "ok" and meta and meta[0] == "2")
        finally:
            conn.close()
    except (OSError, sqlite3.DatabaseError):
        return False


def quarantine_corrupt(root: Path) -> list[Path]:
    """Move corrupt derived artifacts aside before a deterministic rebuild."""
    knowledge = root / ".hornero" / "knowledge"
    candidates = [
        (knowledge / MANIFEST_NAME, _valid_json, "manifest.corrupt.json"),
        (knowledge / FALLBACK_INDEX, _valid_json, "fallback.corrupt.json"),
        (codegraph.db_path(root), _valid_graph, "wiki.corrupt.db"),
    ]
    quarantine = root / ".hornero" / "cache" / "quarantine"
    moved: list[Path] = []
    for path, validator, name in candidates:
        if not path.is_file() or validator(path):
            continue
        quarantine.mkdir(parents=True, exist_ok=True)
        destination = quarantine / name
        if destination.exists():
            destination.unlink()
        path.replace(destination)
        moved.append(destination)
    return moved


def _head_ref(root: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None  # not a git repo: tolerated


def _source_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for base in knowledge_roots(root):
        if base.is_dir():
            files.extend(
                p
                for p in base.rglob("*")
                if p.is_file() and p.suffix.lower() in (".md", ".txt", ".vtt")
            )
    files.extend(codegraph.source_files(root))
    unique = {p.resolve(): p for p in files}
    return sorted(unique.values())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _dump(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def reindex(root: Path) -> dict[str, Any]:
    """Rebuild ``.hornero/knowledge/`` and return the manifest. Fallback
    mode (no parrot — the tested path) is pure tokenization and requires no
    model; PageIndex/GraphIndex delegation arrives once parrot is pinned."""
    knowledge_dir = root / ".hornero" / "knowledge"
    from hornero.memory.ledger import Ledger

    Ledger(root / ".hornero" / "ledger.db").close()
    quarantine_corrupt(root)

    scan = TokenOverlapKnowledge(knowledge_roots(root))
    docs = [
        {
            "path": str(Path(path).resolve().relative_to(root.resolve()))
            if Path(path).resolve().is_relative_to(root.resolve())
            else path,
            "excerpt": excerpt,
            "tokens": sorted(tokens),
        }
        for path, excerpt, tokens in scan.documents()
    ]
    _dump(knowledge_dir / FALLBACK_INDEX, {"schema": 1, "documents": docs})

    graph = codegraph.build_graph(root)

    layers = available()
    layers["codegraph"] = True
    manifest: dict[str, Any] = {
        "schema": 1,
        "head_ref": _head_ref(root),
        "layers": layers,
        "model": None,  # fallback mode is model-free
        "prompt_hash": None,
        "graph": {
            "db": str((root / codegraph.GRAPH_DIR / codegraph.DB_NAME).relative_to(root)),
            "html_report": str(graph.html_report.relative_to(root)) if graph.html_report else None,
            "pages": len(graph.pages),
            "edges": len(graph.edges),
            "sources": len(graph.sources),
            "fts": graph.fts_enabled,
            "skipped": graph.skipped,
            "semantic_entities": graph.semantic_entities,
            "semantic_relations": graph.semantic_relations,
            "provenance": graph.provenance_records,
        },
        "sources": [
            {
                "path": str(p.resolve().relative_to(root.resolve()))
                if p.resolve().is_relative_to(root.resolve())
                else str(p),
                "sha256": _sha256(p),
            }
            for p in _source_files(root)
        ],
    }
    _dump(knowledge_dir / MANIFEST_NAME, manifest)
    from hornero.memory.intelligence import record_snapshot

    manifest["graph"]["snapshot_id"] = record_snapshot(root, manifest)
    _dump(knowledge_dir / MANIFEST_NAME, manifest)
    return manifest


def load_persisted(root: Path) -> TokenOverlapKnowledge | None:
    """Load the persisted fallback index if present (written by reindex)."""
    path = root / ".hornero" / "knowledge" / FALLBACK_INDEX
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    docs = [
        (
            str(root / d["path"]) if not Path(d["path"]).is_absolute() else d["path"],
            d["excerpt"],
            set(d["tokens"]),
        )
        for d in data.get("documents", [])
    ]
    return TokenOverlapKnowledge.from_documents(docs)


def index_staleness(root: Path) -> str:
    """``absent`` | ``fresh`` | ``stale`` | ``corrupt``."""
    manifest_path = root / ".hornero" / "knowledge" / MANIFEST_NAME
    if not manifest_path.is_file():
        return "absent"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return "corrupt"
    if not _valid_graph(codegraph.db_path(root)):
        return "corrupt"
    recorded = {s["path"]: s["sha256"] for s in manifest.get("sources", [])}
    current: dict[str, str] = {}
    for p in _source_files(root):
        rel = (
            str(p.resolve().relative_to(root.resolve()))
            if p.resolve().is_relative_to(root.resolve())
            else str(p)
        )
        current[rel] = _sha256(p)
    return "fresh" if recorded == current else "stale"

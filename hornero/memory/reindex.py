"""``hornero reindex``: the ONLY writer of ``.hornero/knowledge/`` (SPEC-001 §8).

Rebuilds deterministically from ``product/`` + ``.hornero/processed/``:
same repo state => byte-identical artifacts (sorted inputs, sorted JSON
keys, no wall-clock in outputs — provenance is the git ``head_ref``). The
manifest records source content hashes (feeding ``hornero status``
staleness, §13 R3) plus model/prompt hashes (null in fallback mode, which
needs no model at all).
"""

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from hornero.memory.knowledge import (
    TokenOverlapKnowledge,
    available,
    knowledge_roots,
)

MANIFEST_NAME = "manifest.json"
FALLBACK_INDEX = "fallback/index.json"


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
    return sorted(files)


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

    manifest: dict[str, Any] = {
        "schema": 1,
        "head_ref": _head_ref(root),
        "layers": available(),
        "model": None,  # fallback mode is model-free
        "prompt_hash": None,
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
    return manifest


def load_persisted(root: Path) -> TokenOverlapKnowledge | None:
    """Load the persisted fallback index if present (written by reindex)."""
    path = root / ".hornero" / "knowledge" / FALLBACK_INDEX
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
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
    """``absent`` | ``fresh`` | ``stale`` — manifest hashes vs current files."""
    manifest_path = root / ".hornero" / "knowledge" / MANIFEST_NAME
    if not manifest_path.is_file():
        return "absent"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
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

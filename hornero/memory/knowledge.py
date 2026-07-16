"""Knowledge layer: feature detection + first-class fallback (SPEC-001 §8).

``parrot.knowledge.pageindex`` / ``graphindex`` are used when importable
(note the post-FEAT-198 path — never ``parrot.pageindex``); otherwise a
deterministic token-overlap retriever runs. The fallback is a first-class
code path with its own tests, not a stub (CLAUDE.md invariant 5): in a venv
without parrot — the common case — it IS the knowledge layer.
"""

import importlib.util
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from hornero.redact import redact

_TOKEN = re.compile(r"[a-z0-9]+")
_EXCERPT_LEN = 200


def _find(mod: str) -> bool:
    """``find_spec`` guarded against a missing parent package, which raises
    ModuleNotFoundError instead of returning None."""
    try:
        return importlib.util.find_spec(mod) is not None
    except ModuleNotFoundError:
        return False
    except ValueError:  # in sys.modules with __spec__ None (partial import)
        return False


def available() -> dict[str, bool]:
    return {
        "pageindex": _find("parrot.knowledge.pageindex"),
        "graphindex": _find("parrot.knowledge.graphindex"),
        "codegraph": True,
        "fallback": True,
    }


@dataclass(frozen=True)
class Hit:
    path: str
    score: float
    excerpt: str
    kind: str  # "spec" | "decision" | "signal"


@runtime_checkable
class KnowledgeLayer(Protocol):
    def retrieve(self, query: str, k: int = 5) -> list[Hit]: ...


def _tokenize(text: str) -> set[str]:
    return set(_TOKEN.findall(text.lower()))


def _kind_of(path: Path) -> str:
    name = path.name
    if name.startswith("SPEC-"):
        return "spec"
    if name.startswith(("ADR-", "DR-")):
        return "decision"
    return "signal"


class TokenOverlapKnowledge:
    """Deterministic Jaccard-overlap retrieval over ``sdd/**/*.md`` and
    processed signals. Stable tie-break by path. Constructible either from a
    live directory scan or from the persisted index that ``hornero reindex``
    writes (see :mod:`hornero.memory.reindex`)."""

    def __init__(self, roots: list[Path]) -> None:
        self._docs: list[tuple[str, str, set[str]]] = []  # (path, excerpt, tokens)
        for root in roots:
            if not root.is_dir():
                continue
            for path in sorted(root.rglob("*")):
                if path.is_file() and path.suffix.lower() in (".md", ".txt", ".vtt"):
                    text = redact(
                        path.read_text(encoding="utf-8", errors="replace")
                    )
                    self._docs.append(
                        (str(path), text[:_EXCERPT_LEN], _tokenize(text))
                    )

    @classmethod
    def from_documents(
        cls, docs: list[tuple[str, str, set[str]]]
    ) -> "TokenOverlapKnowledge":
        layer = cls([])
        layer._docs = list(docs)
        return layer

    def documents(self) -> list[tuple[str, str, set[str]]]:
        return list(self._docs)

    def retrieve(self, query: str, k: int = 5) -> list[Hit]:
        q = _tokenize(query)
        if not q or not self._docs:
            return []
        scored: list[Hit] = []
        for path, excerpt, tokens in self._docs:
            union = q | tokens
            score = len(q & tokens) / len(union) if union else 0.0
            if score > 0.0:
                scored.append(
                    Hit(path=path, score=score, excerpt=excerpt, kind=_kind_of(Path(path)))
                )
        scored.sort(key=lambda h: (-h.score, h.path))
        return scored[:k]


class PageIndexKnowledge:
    """Thin wrapper over ``parrot.knowledge.pageindex``. Only constructed
    when feature detection succeeds; its real API cannot be verified in a
    parrot-less venv, so treat it as untrusted and let ``open_knowledge``
    degrade to the fallback on any construction failure."""

    def __init__(self, roots: list[Path]) -> None:
        import importlib

        module: Any = importlib.import_module("parrot.knowledge.pageindex")
        self._memory = module.PageIndexDocumentMemory([str(r) for r in roots])

    def retrieve(self, query: str, k: int = 5) -> list[Hit]:
        hits = []
        for item in self._memory.search(query, k):
            hits.append(
                Hit(
                    path=str(item.get("path", "")),
                    score=float(item.get("score", 0.0)),
                    excerpt=str(item.get("excerpt", ""))[:_EXCERPT_LEN],
                    kind=str(item.get("kind", "spec")),
                )
            )
        return hits


class CodeGraphKnowledge:
    """Retriever over Hornero's local SQLite code graph.

    Constructed only when ``hornero reindex`` has written
    ``.hornero/knowledge/graph/wiki.db``. Operational failures degrade to
    the fallback path in :func:`open_knowledge`.
    """

    def __init__(self, root: Path) -> None:
        from hornero.memory import codegraph

        if not codegraph.db_path(root).is_file():
            raise FileNotFoundError(codegraph.db_path(root))
        if not codegraph.stats(root).get("built"):
            raise ValueError("code graph is corrupt or incompatible")
        self._root = root

    def retrieve(self, query: str, k: int = 5) -> list[Hit]:
        from hornero.memory import codegraph

        hits = []
        for item in codegraph.search(self._root, query, limit=k):
            hits.append(
                Hit(
                    path=str(self._root / item.path),
                    score=item.score,
                    excerpt=(item.summary or item.body)[:_EXCERPT_LEN],
                    kind=codegraph._kind_for_path(item.path, item.category),
                )
            )
        return hits


def knowledge_roots(root: Path) -> list[Path]:
    # SPEC-002 §2/§8: the FULL sdd/ corpus is first-class knowledge — specs,
    # proposals, findings under sdd/state/*/findings/, templates, task logs —
    # plus processed signals.
    return [root / "sdd", root / ".hornero" / "processed"]


def open_knowledge(root: Path, config: object = None) -> KnowledgeLayer:
    """Best available layer; the fallback is always constructible and no
    code path hard-requires the parrot indexes (§8)."""
    roots = knowledge_roots(root)
    try:
        return CodeGraphKnowledge(root)
    except Exception:
        pass
    if available()["pageindex"]:
        try:
            return PageIndexKnowledge(roots)
        except Exception:  # degrade gracefully, never hard-require
            pass
    from hornero.memory.reindex import load_persisted  # lazy: avoids cycle

    persisted = load_persisted(root)
    if persisted is not None:
        return persisted
    return TokenOverlapKnowledge(roots)

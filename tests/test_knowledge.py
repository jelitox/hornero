"""Knowledge layer: fallback behavior + feature-detection tests.

The whole file must pass with parrot ABSENT from the venv.
"""

import importlib.machinery
import sys
import types

from hornero.memory.knowledge import (
    Hit,
    KnowledgeLayer,
    TokenOverlapKnowledge,
    available,
    open_knowledge,
)


def _fake_module(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    mod.__spec__ = importlib.machinery.ModuleSpec(name, None)
    return mod


def _corpus(tmp_path):
    specs = tmp_path / "product" / "specs"
    specs.mkdir(parents=True)
    (specs / "SPEC-001-csv-export.md").write_text(
        "Export monthly usage as CSV for finance reconciliation.", encoding="utf-8"
    )
    (specs / "SPEC-002-auth.md").write_text(
        "Single sign-on authentication with OIDC.", encoding="utf-8"
    )
    decisions = tmp_path / "product" / "decisions"
    decisions.mkdir()
    (decisions / "ADR-001-sqlite.md").write_text(
        "We chose SQLite for the ledger.", encoding="utf-8"
    )
    return tmp_path


def test_available_reports_fallback_true_and_no_crash():
    caps = available()
    assert caps["fallback"] is True
    assert caps["pageindex"] is False  # parrot is not installed in this venv
    assert caps["graphindex"] is False


def test_token_overlap_ranks_relevant_doc_first(tmp_path):
    root = _corpus(tmp_path)
    layer = TokenOverlapKnowledge([root / "product"])
    hits = layer.retrieve("monthly CSV export for finance")
    assert hits and hits[0].path.endswith("SPEC-001-csv-export.md")
    assert hits[0].kind == "spec"


def test_kind_classification(tmp_path):
    root = _corpus(tmp_path)
    layer = TokenOverlapKnowledge([root / "product"])
    hits = layer.retrieve("sqlite ledger choice")
    assert hits[0].kind == "decision"


def test_retrieval_deterministic(tmp_path):
    root = _corpus(tmp_path)
    layer = TokenOverlapKnowledge([root / "product"])
    a = layer.retrieve("usage export", k=3)
    b = layer.retrieve("usage export", k=3)
    assert a == b


def test_empty_corpus_and_empty_query(tmp_path):
    layer = TokenOverlapKnowledge([tmp_path / "nope"])
    assert layer.retrieve("anything") == []
    root = _corpus(tmp_path)
    assert TokenOverlapKnowledge([root / "product"]).retrieve("") == []


def test_open_knowledge_falls_back_without_parrot(tmp_path):
    layer = open_knowledge(_corpus(tmp_path))
    assert isinstance(layer, TokenOverlapKnowledge)
    assert isinstance(layer, KnowledgeLayer)


def test_open_knowledge_prefers_pageindex_when_fake_installed(tmp_path, monkeypatch):
    fake = _fake_module("parrot.knowledge.pageindex")

    class PageIndexDocumentMemory:
        def __init__(self, roots):
            self.roots = roots

        def search(self, query, k):
            return [{"path": "x.md", "score": 1.0, "excerpt": "hi", "kind": "spec"}]

    fake.PageIndexDocumentMemory = PageIndexDocumentMemory
    monkeypatch.setitem(sys.modules, "parrot", _fake_module("parrot"))
    monkeypatch.setitem(sys.modules, "parrot.knowledge", _fake_module("parrot.knowledge"))
    monkeypatch.setitem(sys.modules, "parrot.knowledge.pageindex", fake)

    layer = open_knowledge(_corpus(tmp_path))
    assert type(layer).__name__ == "PageIndexKnowledge"
    assert layer.retrieve("q", 1) == [Hit("x.md", 1.0, "hi", "spec")]


def test_open_knowledge_degrades_on_broken_pageindex(tmp_path, monkeypatch):
    broken = _fake_module("parrot.knowledge.pageindex")  # no class inside
    monkeypatch.setitem(sys.modules, "parrot", _fake_module("parrot"))
    monkeypatch.setitem(sys.modules, "parrot.knowledge", _fake_module("parrot.knowledge"))
    monkeypatch.setitem(sys.modules, "parrot.knowledge.pageindex", broken)
    layer = open_knowledge(_corpus(tmp_path))
    assert isinstance(layer, TokenOverlapKnowledge)

# TASK-008: Knowledge layer — feature detection + first-class token-overlap fallback

**Feature**: SPEC-001 — Hornero: foundational contracts and MVP scope
**Spec**: `sdd/specs/SPEC-001-hornero-foundation.md`
**Status**: done
**Priority**: high
**Estimated effort**: L (4-8h)
**Depends-on**: none
**Assigned-to**: unassigned

---

## Context

SPEC-001 §8: mirror the feature-detect/degrade-gracefully pattern. The
reconciler's retrieve step (§9 step 1) needs top-k relevant specs/decisions.
`parrot.knowledge.pageindex`/`graphindex` are used **when importable**;
otherwise a token-overlap retriever. CLAUDE.md invariant 5: the fallback is a
first-class code path with its own tests, not a stub — and in this repo's
venv **parrot is NOT installed**, so the fallback is what actually runs today.

Phase: **F2 — Reconciler** (no dependency on F1 tasks; may start in parallel,
but the F1 gate must be green before F2 *closes*).

---

## Scope

- Implement `hornero/memory/knowledge.py`:
  - `KnowledgeLayer(Protocol)`: `retrieve(query: str, k: int = 5) -> list[Hit]`
    where `Hit` is a small dataclass (`path: str`, `score: float`,
    `excerpt: str`, `kind: str` — `"spec" | "decision" | "signal"`).
  - `available() -> dict[str, bool]` module function reporting which layers
    can load: `{"pageindex": ..., "graphindex": ..., "fallback": True}`.
    Detection via `importlib.util.find_spec("parrot.knowledge.pageindex")`
    etc., wrapped so a missing parent package (`parrot` absent entirely)
    yields `False`, **not** an exception (`find_spec` raises
    `ModuleNotFoundError` when the PARENT is missing — verified; handle it).
  - `TokenOverlapKnowledge(roots: list[Path])` — the fallback: scans
    `product/**/*.md` and `.hornero/processed/*`, tokenizes (lowercase,
    alphanumeric split), scores query↔document overlap (Jaccard or
    TF-weighted — pick one, document it), returns top-k deterministically
    (stable tie-break by path).
  - `PageIndexKnowledge` / `GraphIndexKnowledge` thin wrappers, imported
    lazily and only if `available()` says so. In this environment they
    CANNOT be unit-tested against the real parrot — test the selection logic
    with monkeypatched fake modules instead.
  - `open_knowledge(root: Path, config) -> KnowledgeLayer` — resolver:
    best available layer, fallback always constructible. **No code path may
    hard-require the indexes** (§8).
- Tests in `tests/test_knowledge.py` (fallback behavior + selection logic).

**NOT in scope**: `hornero reindex` / persisted index building + manifest
(TASK-016), reconciler prompting (TASK-009), report generation (F5).

---

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `hornero/memory/knowledge.py` | CREATE | protocol, detection, fallback, wrappers, resolver |
| `tests/test_knowledge.py` | CREATE | fallback + feature-detection tests |

---

## Codebase Contract (Anti-Hallucination)

> **CRITICAL**: verified against the repo AND venv on 2026-07-06.

### Verified Imports
```python
import importlib.util               # stdlib — find_spec for detection
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable
```

### Existing Signatures to Use
```python
# VERIFIED environment facts (2026-07-06):
#   importlib.util.find_spec("parrot")            -> None (NOT installed)
#   importlib.util.find_spec("parrot.knowledge.pageindex")
#       -> raises ModuleNotFoundError (parent missing) — MUST be caught
# hornero/memory/ package: created by TASK-004; if picking this up before
# TASK-004 lands, create hornero/memory/__init__.py yourself (empty) — it is
# a trivial shared file, coordinate via git.
```

### Does NOT Exist
- ~~`parrot` in this venv~~ — NOT installed; ALL parrot imports must be lazy
  and guarded; the test suite must pass with parrot absent
- ~~`parrot.pageindex`~~ — wrong path even when parrot IS installed
  (CLAUDE.md invariant 5): the correct post-FEAT-198 path is
  `parrot.knowledge.pageindex`
- ~~`PageIndexDocumentMemory` importable here~~ — cannot be verified in this
  environment; wrapper code must treat its API as untrusted and be exercised
  only via fakes
- ~~embedding/vector libs (numpy, faiss, sentence-transformers)~~ — not
  installed; the fallback is pure-Python token overlap

---

## Implementation Notes

### Pattern to Follow
```python
def _find(mod: str) -> bool:
    try:
        return importlib.util.find_spec(mod) is not None
    except ModuleNotFoundError:   # parent package absent
        return False
```

### Key Constraints
- Deterministic retrieval (invariant 6): fixed tokenization, stable sort.
- The fallback must handle empty roots (no product/ yet) by returning `[]`.
- Selection tests monkeypatch `sys.modules` with fakes to simulate parrot
  presence — never skip-if-installed logic that silently reduces coverage.

### References in Codebase
- SPEC-001 §8 (layer table + rules), §9 step 1 (consumer), CLAUDE.md
  invariant 5 (import path + first-class fallback).

---

## Acceptance Criteria

- [ ] `available()` returns `{"pageindex": False, "graphindex": False, "fallback": True}` in this venv without raising
- [ ] `TokenOverlapKnowledge` returns relevant doc first on a fixture corpus; deterministic across runs
- [ ] `open_knowledge` returns the fallback when parrot is absent; returns the fake pageindex wrapper when a fake module is injected
- [ ] Entire suite passes with parrot absent: `pytest tests/test_knowledge.py -q`
- [ ] `ruff check` + `mypy hornero` clean

---

## Test Specification

```python
# tests/test_knowledge.py
from hornero.memory.knowledge import TokenOverlapKnowledge, available, open_knowledge


def test_available_reports_fallback_true_and_no_crash(): ...
def test_token_overlap_ranks_relevant_doc_first(tmp_path): ...
def test_retrieval_deterministic(tmp_path): ...
def test_empty_corpus_returns_empty(tmp_path): ...
def test_open_knowledge_prefers_pageindex_when_fake_installed(tmp_path, monkeypatch): ...
```

---

## Agent Instructions

When you pick up this task:

1. **Read the spec** at the path listed above for full context
2. **Check dependencies** — none (coordinate on `hornero/memory/__init__.py` with TASK-004)
3. **Verify the Codebase Contract** — before writing ANY code
4. **Update status** in `sdd/tasks/index/hornero-foundation.json` → `"in-progress"`
5. **Implement** following the scope, codebase contract, and notes above
6. **Verify** all acceptance criteria are met
7. **Move this file** to `sdd/tasks/completed/TASK-008-knowledge-layer-fallback.md`
8. **Update index** → `"done"`
9. **Fill in the Completion Note** below

---

## Completion Note

**Completed by**: claude-fable-5 (session 0d52d2f9)
**Date**: 2026-07-06
**Notes**: hornero/memory/knowledge.py: available() with guarded find_spec (ModuleNotFoundError + ValueError), Hit/KnowledgeLayer protocol, TokenOverlapKnowledge (Jaccard, stable tie-break, kind by filename prefix), PageIndexKnowledge lazy wrapper, open_knowledge resolver degrading gracefully on broken/absent parrot. 8 tests green with parrot absent.

**Deviations from spec**: none

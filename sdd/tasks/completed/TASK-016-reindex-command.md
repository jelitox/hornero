# TASK-016: `hornero reindex` — deterministic knowledge rebuild + manifest

**Feature**: SPEC-001 — Hornero: foundational contracts and MVP scope
**Spec**: `sdd/specs/SPEC-001-hornero-foundation.md`
**Status**: done
**Priority**: medium
**Estimated effort**: M (2-4h)
**Depends-on**: TASK-007, TASK-008
**Assigned-to**: unassigned

---

## Context

SPEC-001 §8: `hornero reindex` is **the only writer** of
`.hornero/knowledge/`; it rebuilds deterministically from `product/` +
`.hornero/processed/`, recording model + prompt hashes in an index manifest
for reproducibility. `.hornero/knowledge/` is committed (§4) so the repo is
clonable with memory included. Also feeds `hornero status` staleness (R3).

Phase: **F4 — Write-back**.

---

## Scope

- Implement `hornero/memory/reindex.py`:
  - `reindex(root: Path, config, llm: LLMPort | None, clock) -> IndexManifest`:
    - Fallback mode (parrot absent — the reality in this venv): build the
      token-overlap index as committed JSON artifacts under
      `.hornero/knowledge/fallback/` (tokenized doc table + metadata). The
      fallback layer (TASK-008) gains a constructor that loads this
      persisted form when present (falling back to live scan when not).
    - PageIndex/GraphIndex mode: when feature-detected AND a summary model is
      configured, delegate tree/graph building to the parrot APIs — wrapped,
      lazy, tested via fakes only.
    - Write `.hornero/knowledge/manifest.json`: source file list with content
      hashes, `head_ref` (current git HEAD via `git rev-parse HEAD`,
      subprocess, tolerate non-git dirs), model id + prompt hash (or nulls in
      fallback mode), layer availability snapshot.
    - **Deterministic**: same repo state ⇒ byte-identical index + manifest
      (sort everything; no timestamps in artifacts — the manifest records
      `head_ref`, not wall-clock).
  - Wire the `reindex` CLI stub (TASK-007) to this function.
  - Upgrade `hornero status` index-health line: compare manifest source
    hashes vs current files ⇒ `fresh | stale | absent` (replaces the
    `unknown` placeholder from TASK-007).
- Tests in `tests/test_reindex.py`: determinism (run twice ⇒ identical
  bytes), staleness detection, only-writer property (nothing else in the
  suite writes `.hornero/knowledge/` — assert reconcile/build leave it
  untouched).

**NOT in scope**: the merge-trigger hook (TASK-017), report generation (F5),
DUPLICATE detection behavior (TASK-017 asserts it e2e).

---

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `hornero/memory/reindex.py` | CREATE | reindex + manifest |
| `hornero/memory/knowledge.py` | MODIFY | fallback loads persisted index |
| `hornero/cli.py` | MODIFY | wire real `reindex`; status staleness |
| `tests/test_reindex.py` | CREATE | determinism + staleness tests |

---

## Codebase Contract (Anti-Hallucination)

> **CRITICAL**: verified against the repo AND venv on 2026-07-06.

### Verified Imports
```python
import hashlib, json, subprocess
from hornero.memory.knowledge import TokenOverlapKnowledge, available  # TASK-008
from hornero.config import load_config                                  # TASK-007
```

### Existing Signatures to Use
```python
# hornero/memory/knowledge.py (TASK-008) — read the real file on pickup;
# you are MODIFYING it (persisted-index loading), keep its tests green.
# hornero/cli.py (TASK-007) — status prints "knowledge index: unknown";
# replace with fresh|stale|absent.
```

### Does NOT Exist
- ~~`parrot` in this venv~~ — fallback mode is the tested, primary path;
  parrot delegation only via injected fakes
- ~~a summary-model requirement in fallback mode~~ — fallback reindex must
  run with `llm=None` (no model configured) — it's pure tokenization
- ~~incremental indexing~~ — MVP rebuilds from scratch every time
  (determinism over speed)

---

## Implementation Notes

### Key Constraints
- The determinism guarantee is the WHOLE point (§8): "deterministic given the
  repo state plus the configured summary model". Sort file lists, use
  `sort_keys=True` JSON, LF endings, no floats from timing.
- `git rev-parse` failure (not a repo) ⇒ `head_ref: null`, not an error.
- Committed artifacts must be reviewable: pretty-printed JSON, stable order.

### References in Codebase
- SPEC-001 §4 (knowledge committed), §8 (only-writer + manifest), §13 R3
  (staleness surfacing).

---

## Acceptance Criteria

- [ ] Two consecutive `reindex` runs on an unchanged repo produce byte-identical `.hornero/knowledge/` (assert via tree hash)
- [ ] Manifest records source hashes + head_ref; fallback mode records null model
- [ ] `hornero status` reports `fresh` after reindex, `stale` after editing a spec, `absent` before first run
- [ ] Retrieval through the persisted fallback index equals live-scan results
- [ ] All tests pass: `pytest tests/test_reindex.py -q`; `ruff check` + `mypy hornero` clean

---

## Test Specification

```python
# tests/test_reindex.py
from hornero.memory.reindex import reindex


def test_reindex_deterministic_bytes(tmp_path): ...
def test_manifest_contents(tmp_path): ...
def test_status_staleness_lifecycle(tmp_path): ...
def test_persisted_index_matches_live_scan(tmp_path): ...
def test_non_git_dir_tolerated(tmp_path): ...
```

---

## Agent Instructions

When you pick up this task:

1. **Read the spec** at the path listed above for full context
2. **Check dependencies** — verify TASK-007, TASK-008 are in `sdd/tasks/completed/`
3. **Verify the Codebase Contract** — before writing ANY code
4. **Update status** in `sdd/tasks/index/hornero-foundation.json` → `"in-progress"`
5. **Implement** following the scope, codebase contract, and notes above
6. **Verify** all acceptance criteria are met
7. **Move this file** to `sdd/tasks/completed/TASK-016-reindex-command.md`
8. **Update index** → `"done"`
9. **Fill in the Completion Note** below

---

## Completion Note

**Completed by**: claude-fable-5 (session 0d52d2f9)
**Date**: 2026-07-06
**Notes**: hornero/memory/reindex.py: deterministic rebuild (sorted inputs, sorted JSON, no wall-clock in artifacts), manifest with source sha256 + head_ref + layer snapshot + null model/prompt in fallback mode, load_persisted() equivalence with live scan, index_staleness absent/fresh/stale wired into hornero status; reindex CLI real. 7 tests; full suite 123 passed.

**Deviations from spec**: none

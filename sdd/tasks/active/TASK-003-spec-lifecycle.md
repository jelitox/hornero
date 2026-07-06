# TASK-003: Spec lifecycle — frontmatter contract + state machine + `SpecCorpus`

**Feature**: SPEC-001 — Hornero: foundational contracts and MVP scope
**Spec**: `sdd/specs/SPEC-001-hornero-foundation.md`
**Status**: pending
**Priority**: high
**Estimated effort**: L (4-8h)
**Depends-on**: none
**Assigned-to**: unassigned

---

## Context

SPEC-001 §5 defines the repo-native spec state machine — spec files under
`product/specs/` ARE the tracker (G4). This module owns parsing/serializing
the YAML frontmatter contract, validating status transitions, and loading the
corpus. It is the direct subject of the F1 gate test `tests/test_lifecycle.py`.

Phase: **F1 — Skeleton**.

---

## Scope

- Add `pyyaml` to `[project] dependencies` in `pyproject.toml` (first runtime
  dependency — deliberate; frontmatter is YAML per SPEC-001 §5).
- Implement `hornero/lifecycle.py`:
  - `Status(StrEnum)`: `proposed, approved, building, review, done, rejected,
    needs_human, obsolete` (SPEC-001 §5).
  - `TRANSITIONS: dict[Status, set[Status]]` encoding exactly the §5 diagram:
    `proposed→{approved, rejected}`, `approved→{building}`,
    `building→{review, needs_human}`, `review→{done}`, plus `→obsolete`
    reachable from any non-terminal state (set by an approved OBSOLETE
    delta). Terminal: `done, rejected, obsolete` (and `needs_human` until a
    human intervenes — model it as re-enterable to `approved`).
  - `SpecDoc` dataclass: `spec_id, title, status, kind, created, sources,
    supersedes, acceptance_criteria, body, path` — parsed from a spec file's
    frontmatter + markdown body per the §5 frontmatter contract.
  - `parse_spec(path) -> SpecDoc` / `write_spec(doc) -> None` — round-trip
    safe: re-serializing an unmodified doc produces byte-identical output
    (required so `--dry-run` and `transition()` diffs stay minimal).
  - `transition(doc, new_status) -> SpecDoc` — validates against
    `TRANSITIONS`, raises `IllegalTransition` otherwise.
  - `SpecCorpus`: loads all `SPEC-*.md` under a specs dir; `next_spec_id()`
    returns the next monotonic ID (`SPEC-001`, `SPEC-002`, … per §4 rules);
    lookup by id.
- Tests in `tests/test_lifecycle.py` (**this is an F1 gate file — the exact
  path is fixed by the spec's phase table, do not rename**).

**NOT in scope**: `TrackerPort` adapter semantics (`upsert/comment` — that is
`RepoTracker`, TASK-006), acceptance-criteria *parsing into criterion objects*
(TASK-013), delta application (TASK-011).

---

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `hornero/lifecycle.py` | CREATE | Status, TRANSITIONS, SpecDoc, SpecCorpus |
| `tests/test_lifecycle.py` | CREATE | F1 gate test file |
| `pyproject.toml` | MODIFY | add `pyyaml` to dependencies |

---

## Codebase Contract (Anti-Hallucination)

> **CRITICAL**: verified against the repo on 2026-07-06.

### Verified Imports
```python
from dataclasses import dataclass, field  # stdlib
from enum import StrEnum                  # stdlib, py>=3.11
from pathlib import Path                  # stdlib
import yaml  # ONLY after adding pyyaml to pyproject and `uv pip install -e '.[dev]'`
```

### Existing Signatures to Use
```python
# pyproject.toml (verified): dependencies = []  ← you MODIFY this line
# .venv (verified): pyyaml NOT installed yet — install after editing pyproject:
#   source .venv/bin/activate && uv pip install -e '.[dev]'
```

### Does NOT Exist
- ~~`yaml` in the venv today~~ — importable only after the pyproject edit + reinstall
- ~~`python-frontmatter` package~~ — not installed; parse frontmatter manually
  (split on `---` fences) + `yaml.safe_load`
- ~~`hornero.ports`, `hornero.models`~~ — may not exist yet (parallel tasks);
  this module must not import them
- ~~`ruamel.yaml`~~ — not installed; byte-identical round-trip must be achieved
  by preserving the original frontmatter text when unchanged, not by a
  format-preserving YAML library

---

## Implementation Notes

### Pattern to Follow
The frontmatter contract to parse, verbatim from SPEC-001 §5:
```yaml
---
spec: SPEC-004
title: Export monthly usage as CSV
status: approved
kind: new_feature
created: 2026-07-06
sources: [sig-20260706-a1]
supersedes: []
acceptance_criteria:
  - "pytest tests/export/test_csv.py -q"
  - "manual: CSV opens correctly in LibreOffice"
---
```

### Key Constraints
- **Round-trip stability**: keep the raw frontmatter string on `SpecDoc`;
  when only `status` changes, rewrite just that line. `--dry-run` (F2 gate)
  requires `git status` clean after a no-op pass.
- Unknown `status` values in a file ⇒ raise, don't coerce (fail-closed).
- `yaml.safe_load` only — never `yaml.load`.
- ID allocation scans existing files; no counter file (repo is the SSOT §4).

### References in Codebase
- SPEC-001 §5 (state machine + frontmatter), §4 (monotonic IDs).
- This repo's own `sdd/specs/SPEC-001-hornero-foundation.md` frontmatter is a
  live example of the format (note: `owner`/`depends_on` extras must be
  preserved on round-trip, not dropped).

---

## Acceptance Criteria

- [ ] Frontmatter round-trip is byte-identical for an unmodified doc
- [ ] Every edge in the §5 diagram is allowed; every non-edge raises `IllegalTransition`
- [ ] `SpecCorpus.next_spec_id()` returns `SPEC-001` on an empty dir, `SPEC-003` when 001–002 exist
- [ ] Unknown status in a file raises (fail-closed)
- [ ] All tests pass: `pytest tests/test_lifecycle.py -q` (F1 gate component)
- [ ] `ruff check hornero/lifecycle.py` and `mypy hornero` clean

---

## Test Specification

```python
# tests/test_lifecycle.py
import pytest
from hornero.lifecycle import IllegalTransition, SpecCorpus, Status, parse_spec, transition, write_spec


def test_roundtrip_byte_identical(tmp_path): ...
def test_legal_path_proposed_to_done(tmp_path): ...        # proposed→approved→building→review→done
def test_illegal_transition_raises(tmp_path):
    # e.g. proposed → building must raise IllegalTransition
    ...
def test_obsolete_reachable_from_nonterminal(tmp_path): ...
def test_monotonic_ids(tmp_path): ...
def test_unknown_status_fails_closed(tmp_path): ...
```

---

## Agent Instructions

When you pick up this task:

1. **Read the spec** at the path listed above for full context
2. **Check dependencies** — none for this task
3. **Verify the Codebase Contract** — before writing ANY code
4. **Update status** in `sdd/tasks/index/hornero-foundation.json` → `"in-progress"`
5. **Implement** following the scope, codebase contract, and notes above
6. **Verify** all acceptance criteria are met
7. **Move this file** to `sdd/tasks/completed/TASK-003-spec-lifecycle.md`
8. **Update index** → `"done"`
9. **Fill in the Completion Note** below

---

## Completion Note

*(Agent fills this in when done)*

**Completed by**:
**Date**:
**Notes**:

**Deviations from spec**: none

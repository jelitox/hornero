# TASK-004: SQLite ledger — runs, deltas, verdicts, checkpoints

**Feature**: SPEC-001 — Hornero: foundational contracts and MVP scope
**Spec**: `sdd/specs/SPEC-001-hornero-foundation.md`
**Status**: pending
**Priority**: high
**Estimated effort**: M (2-4h)
**Depends-on**: none
**Assigned-to**: unassigned

---

## Context

SPEC-001 §4 places operational state in `.hornero/ledger.db` (SQLite,
gitignored — already covered by this repo's `.gitignore` pattern). The ledger
is the audit backbone: dropped drafts (`evidence_mismatch`, invariant 1),
DUPLICATE deltas ("persisted for audit, never dispatched", §6), dispatch
results with PR URLs (F3 gate), and the traceability report (F5) all read or
write it.

Phase: **F1 — Skeleton**.

---

## Scope

- Implement `hornero/memory/__init__.py` and `hornero/memory/ledger.py`:
  - `Ledger` class wrapping a SQLite file; `Ledger(path)` creates the schema
    idempotently (`CREATE TABLE IF NOT EXISTS`).
  - Tables (minimum viable, extend as needed):
    - `runs(run_id TEXT PK, command TEXT, started_at REAL, finished_at REAL, dry_run INTEGER)`
    - `deltas(delta_id TEXT PK, run_id, kind, title, status, confidence REAL, payload_json TEXT)`
    - `dropped_drafts(id INTEGER PK AUTOINCREMENT, run_id, reason TEXT, payload_json TEXT, created_at REAL)`
      — `reason` values include `evidence_mismatch`
    - `verdicts(id INTEGER PK AUTOINCREMENT, delta_id, judge TEXT, vote TEXT, payload_json TEXT)`
    - `dispatches(id INTEGER PK AUTOINCREMENT, spec_id TEXT, run_id, status TEXT, pr_url TEXT, branch TEXT, log_path TEXT, created_at REAL)`
    - `checkpoints(key TEXT PK, value_json TEXT, updated_at REAL)`
  - Typed append/query methods (e.g. `record_run`, `record_delta`,
    `record_dropped_draft(reason, payload)`, `record_dispatch`,
    `trace(spec_id)` returning the signal→delta→spec→PR chain rows).
  - Context-manager support; WAL mode; all timestamps injected by callers
    (deterministic tests — no `time.time()` inside query methods' defaults).
- Tests in `tests/test_ledger.py` using `tmp_path`.

**NOT in scope**: knowledge indexes (`.hornero/knowledge/` is TASK-008/016),
who calls `record_dropped_draft` (TASK-009), report rendering (TASK-019).

---

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `hornero/memory/__init__.py` | CREATE | package marker |
| `hornero/memory/ledger.py` | CREATE | Ledger class + schema |
| `tests/test_ledger.py` | CREATE | schema, append, trace, idempotency tests |

---

## Codebase Contract (Anti-Hallucination)

> **CRITICAL**: verified against the repo on 2026-07-06.

### Verified Imports
```python
import sqlite3      # stdlib
import json         # stdlib
from pathlib import Path
```

### Existing Signatures to Use
```python
# .gitignore (verified) already contains: .hornero/ledger.db
# hornero/ package (verified): only an empty __init__.py — hornero/memory/ does not exist yet
```

### Does NOT Exist
- ~~`sqlalchemy`, `aiosqlite`~~ — not installed; stdlib `sqlite3`, synchronous
- ~~`hornero.models`~~ — may not exist yet (parallel TASK-002); the ledger
  stores JSON payloads (`dataclasses.asdict` done by CALLERS), it must not
  import the delta model
- ~~`.hornero/` directory in this repo~~ — created at runtime by `hornero init`
  (TASK-007); tests use `tmp_path`

---

## Implementation Notes

### Key Constraints
- Schema creation idempotent: constructing `Ledger` twice on the same file
  must not fail or duplicate anything.
- No ORM, no migrations framework — a `schema_version` row in `checkpoints`
  is enough for MVP.
- Determinism (CLAUDE.md invariant 6): methods take explicit timestamps;
  convenience defaults may exist but tests always inject.
- `payload_json` columns keep the ledger forward-compatible with model
  changes; never store pickled objects.

### References in Codebase
- SPEC-001 §4 (ledger placement), §6 (DUPLICATE audit rule), §9 step 2
  (`evidence_mismatch`), §11 (`traceability.html` "falls out of the ledger
  for free" — `trace()` is what makes that true).

---

## Acceptance Criteria

- [ ] `Ledger(tmp_path / "ledger.db")` creates all tables; second construction is a no-op
- [ ] `record_dropped_draft(reason="evidence_mismatch", ...)` round-trips via a query method
- [ ] `trace(spec_id)` joins deltas + dispatches for a spec
- [ ] All tests pass: `pytest tests/test_ledger.py -q`
- [ ] `ruff check hornero/memory/` and `mypy hornero` clean

---

## Test Specification

```python
# tests/test_ledger.py
from hornero.memory.ledger import Ledger


def test_schema_idempotent(tmp_path): ...
def test_record_and_query_dropped_draft(tmp_path): ...
def test_record_dispatch_and_trace(tmp_path): ...
def test_checkpoint_upsert(tmp_path): ...
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
7. **Move this file** to `sdd/tasks/completed/TASK-004-ledger-store.md`
8. **Update index** → `"done"`
9. **Fill in the Completion Note** below

---

## Completion Note

*(Agent fills this in when done)*

**Completed by**:
**Date**:
**Notes**:

**Deviations from spec**: none

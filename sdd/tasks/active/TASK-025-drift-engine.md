# TASK-025: Three-way drift engine (§6)

**Feature**: SPEC-002 — SDD toolkit: install, memory bootstrap, and cross-repo sync
**Spec**: `sdd/specs/SPEC-002-sdd-toolkit-sync.md`
**Status**: pending
**Priority**: high
**Estimated effort**: M (2-4h)
**Depends-on**: TASK-020, TASK-021, TASK-022
**Assigned-to**: unassigned

---

## Context

SPEC-002 §6: per managed file compare U (upstream now), L (lock
`installed_hash`), C (current on disk) into six states. Hard rule
(CLAUDE.md invariant 4): **diverged files are never auto-resolved** — no
timestamp heuristics. Phase F3.5.

## Scope

- `hornero/sdd_toolkit/drift.py`:
  - `DriftState(StrEnum)`: `CURRENT, BEHIND, MODIFIED, DIVERGED,
    DELETED_LOCALLY, NEW_UPSTREAM` (+ `HELD` for policy=local,
    `PINNED` for policy=pinned — reported, never pulled).
  - `@dataclass FileDrift`: `path`, `state`, `upstream_hash: str | None`,
    `installed_hash: str | None`, `current_hash: str | None`.
  - `classify(upstream_root, repo_root, manifest, lock) -> list[FileDrift]`
    — union of managed-set files and lock entries, sorted by path;
    files in upstream but not in lock ⇒ `NEW_UPSTREAM`.
  - `apply_pull(drifts, upstream_root, repo_root, lock, *, force=False)
    -> PullReport` — per §6 table: BEHIND ⇒ copy + update lock;
    NEW_UPSTREAM ⇒ install + lock; DELETED_LOCALLY ⇒ reinstall only with
    `force`; MODIFIED/CURRENT/HELD/PINNED ⇒ nothing; DIVERGED ⇒ listed in
    `report.diverged`, file untouched. Pure filesystem, no prompting.
- Tests `tests/test_sdd_drift.py` — the full §6 matrix.

**NOT in scope**: CLI rendering (TASK-026), --theirs/--ours resolution
(TASK-026 passes explicit choices), push (TASK-027).

## Codebase Contract (Anti-Hallucination)

```python
from hornero.sdd_toolkit.lock import SddLock, FileEntry, sha256_file, save_lock
from hornero.sdd_toolkit.manifest import Manifest, resolve_managed
# No merge library exists or is wanted: diverged == report-only.
```

## Acceptance Criteria

- [ ] All six §6 states classified correctly on a fixture matrix
- [ ] `apply_pull` performs exactly the table's actions; diverged file bytes untouched
- [ ] policy `local`/`pinned` files are never copied over
- [ ] `pytest tests/test_sdd_drift.py -q` green; ruff + mypy clean

## Test Specification

```python
def test_matrix_all_six_states(tmp_path): ...
def test_pull_fast_forwards_behind_and_new(tmp_path): ...
def test_pull_never_touches_diverged_or_modified(tmp_path): ...
def test_deleted_locally_requires_force(tmp_path): ...
def test_policies_hold_and_pin(tmp_path): ...
```

---

## Completion Note

*(Agent fills this in when done)*

**Completed by**:
**Date**:
**Notes**:

**Deviations from spec**: none

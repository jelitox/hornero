# TASK-022: Per-repo lockfile — `.hornero/sdd.lock`

**Feature**: SPEC-002 — SDD toolkit: install, memory bootstrap, and cross-repo sync
**Spec**: `sdd/specs/SPEC-002-sdd-toolkit-sync.md`
**Status**: done
**Priority**: high
**Estimated effort**: S (< 2h)
**Depends-on**: none
**Assigned-to**: unassigned

---

## Context

SPEC-002 §5: the lockfile records per managed file `upstream_hash`,
`installed_hash`, `policy` (`sync` | `local` | `pinned`), plus upstream
identity (url/ref/version/commit/synced_at). Written by `install` and every
successful `sync`; it is the L leg of the three-way drift model (§6).
Phase F2.5.

## Scope

- `hornero/sdd_toolkit/lock.py`:
  - `@dataclass FileEntry`: `upstream_hash: str`, `installed_hash: str`,
    `policy: str = "sync"` (validate against the three legal values).
  - `@dataclass SddLock`: `upstream`, `upstream_ref`, `toolkit_version`,
    `upstream_commit: str | None`, `synced_at: str`,
    `files: dict[str, FileEntry]`.
  - `load_lock(repo_root) -> SddLock | None`; `save_lock(repo_root, lock)`
    — sorted keys, trailing newline, deterministic bytes.
  - `sha256_file(path) -> str` helper (shared by install/drift).
  - `set_policy(lock, file, policy)` — unknown file or illegal policy ⇒
    `ValueError` (fail-closed).
- Tests `tests/test_sdd_lock.py` (round-trip byte-identical, policy
  validation, missing lock ⇒ None).

**NOT in scope**: drift classification (TASK-025), CLI (TASK-023/026).

## Codebase Contract (Anti-Hallucination)

```python
# stdlib json/hashlib/dataclasses. `.hornero/sdd.lock` must be COMMITTED
# (it is the sync identity) — verify .gitignore does NOT cover it: the
# ignore pattern is '.hornero/ledger.db*' and '.hornero/cache/' only
# (verified 2026-07-07).
```

### Does NOT Exist
- ~~pydantic~~ — dataclasses + manual validation

## Acceptance Criteria

- [ ] Save→load round-trip identical; second save byte-identical
- [ ] Illegal policy raises; unknown file in `set_policy` raises
- [ ] `pytest tests/test_sdd_lock.py -q` green; ruff + mypy clean

## Test Specification

```python
def test_roundtrip_and_deterministic_bytes(tmp_path): ...
def test_missing_lock_returns_none(tmp_path): ...
def test_policy_validation(tmp_path): ...
def test_sha256_file(tmp_path): ...
```

---

## Completion Note

**Completed by**: claude-fable-5 (session 0d52d2f9)
**Date**: 2026-07-06
**Notes**: hornero/sdd_toolkit/lock.py: FileEntry (policy-validated), SddLock, deterministic save/load round-trip, sha256_file, set_policy fail-closed. Lockfile intentionally NOT gitignored (sync identity, committed). 4 tests green.

**Deviations from spec**: none

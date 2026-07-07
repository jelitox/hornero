# TASK-021: Upstream fetcher — sparse/shallow clone cache

**Feature**: SPEC-002 — SDD toolkit: install, memory bootstrap, and cross-repo sync
**Spec**: `sdd/specs/SPEC-002-sdd-toolkit-sync.md`
**Status**: done
**Priority**: high
**Estimated effort**: M (2-4h)
**Depends-on**: none
**Assigned-to**: unassigned

---

## Context

SPEC-002 §7 mechanics: upstream access is a shallow clone
(`--filter=blob:none`) into `.hornero/cache/sdd-upstream/`, refreshed on
each `status`/`sync`, usable offline against the cache with a staleness
warning. `--from` also accepts a **local path** (G5 + deterministic tests:
fixture upstreams are directories). Phase F2.5.

## Scope

- `hornero/sdd_toolkit/upstream.py`:
  - `@dataclass Checkout`: `root: Path`, `commit: str | None`,
    `refreshed: bool` (False ⇒ offline/cache-stale, caller warns).
  - `fetch_upstream(source: str, ref: str, repo_root: Path) -> Checkout`:
    - local directory source ⇒ use in place; `commit` via
      `git -C <src> rev-parse HEAD` when it is a git repo, else None.
    - git URL ⇒ clone `--filter=blob:none --depth 1 --branch <ref>` into
      `.hornero/cache/sdd-upstream/`; if cache exists, `fetch` + reset to
      `origin/<ref>`; network failure with existing cache ⇒ return cache
      with `refreshed=False`; network failure without cache ⇒ raise
      `UpstreamError`.
  - All git via `subprocess.run(check=True, capture_output=True)`; no
    GitPython (not installed).
- Tests `tests/test_sdd_upstream.py` — local-dir sources and a local git
  repo as "remote" URL (file path clones work with git); simulate network
  failure with a bogus URL + pre-seeded cache.

**NOT in scope**: manifest parsing (TASK-020), file copying (TASK-023).

## Codebase Contract (Anti-Hallucination)

```python
# stdlib subprocess/pathlib only. .hornero/cache/ is already gitignored
# (verified: .gitignore has .hornero/cache/). Cloning a local path with
# --filter=blob:none works with modern git (verified locally, git >= 2.30).
```

### Does NOT Exist
- ~~GitPython, dulwich~~ — not installed
- ~~a daemon/watcher~~ — refresh happens inline per command

## Acceptance Criteria

- [ ] Local dir source used in place; git-repo dir yields its HEAD sha
- [ ] URL clone lands in `.hornero/cache/sdd-upstream/` and re-fetch refreshes
- [ ] Bogus URL + warm cache ⇒ `refreshed=False`, no raise; cold ⇒ `UpstreamError`
- [ ] `pytest tests/test_sdd_upstream.py -q` green; ruff + mypy clean

## Test Specification

```python
def test_local_dir_source(tmp_path): ...
def test_local_git_repo_source_has_commit(tmp_path): ...
def test_url_clone_into_cache_and_refresh(tmp_path): ...
def test_offline_with_cache_warns_not_raises(tmp_path): ...
def test_offline_without_cache_raises(tmp_path): ...
```

---

## Completion Note

**Completed by**: claude-fable-5 (session 0d52d2f9)
**Date**: 2026-07-06
**Notes**: hornero/sdd_toolkit/upstream.py: local dirs in place (HEAD recorded when git), URLs blobless-shallow-cloned into .hornero/cache/sdd-upstream/ with fetch+detach refresh; warm-cache network failure degrades to refreshed=False; cold failure raises UpstreamError and leaves no half clone. 5 tests green (file:// fixtures).

**Deviations from spec**: none

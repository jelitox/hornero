# TASK-023: `hornero sdd install` — installer + scaffold + adopt (F2.5 gate closer)

**Feature**: SPEC-002 — SDD toolkit: install, memory bootstrap, and cross-repo sync
**Spec**: `sdd/specs/SPEC-002-sdd-toolkit-sync.md`
**Status**: done
**Priority**: high
**Estimated effort**: L (4-8h)
**Depends-on**: TASK-020, TASK-021, TASK-022
**Assigned-to**: unassigned

---

## Context

SPEC-002 G1 + §7: one command makes any repo SDD-capable — toolkit files +
state skeleton + lockfile. On a repo with hand-copied SDD files it ADOPTS
them (hash match ⇒ current; mismatch ⇒ recorded as modified, not
clobbered); overwrites only with `--force`. **Closes the F2.5 phase gate.**

## Scope

- `hornero/sdd_toolkit/install.py`:
  - `install(repo_root, source, ref, *, force=False, synced_at, echo) -> int`:
    1. `fetch_upstream` (TASK-021); warn when `refreshed=False`.
    2. `load_manifest` (TASK-020); warn when fallback.
    3. Per managed file: absent locally ⇒ copy + lock (`installed ==
       upstream` hash). Present + hash equal ⇒ adopt as current. Present +
       differs ⇒ keep local file, lock records local `installed_hash`
       (state will read `modified`) unless `--force` (copy upstream).
    4. Scaffold dirs from manifest `scaffold` with `.gitkeep`.
    5. `save_lock`.
- CLI: `hornero sdd install [--from <url|path>] [--ref <ref>] [--force]` —
  `sdd` subcommand group added to `hornero/cli.py`. `--from` defaults to
  config key `sdd_upstream:` (add to `hornero/config.py`, default "" ⇒
  install requires an explicit `--from`; fail-closed, no surprise network).
- Tests `tests/test_sdd_install.py` with a **fixture upstream directory**
  (mini toolkit: 2 commands, 1 rule, WORKFLOW.md, 1 template + manifest).

**NOT in scope**: drift table/status (TASK-025/026), `hornero init`
integration (TASK-024), push (TASK-027).

## Codebase Contract (Anti-Hallucination)

```python
from hornero.sdd_toolkit.manifest import load_manifest, resolve_managed  # TASK-020
from hornero.sdd_toolkit.upstream import fetch_upstream                  # TASK-021
from hornero.sdd_toolkit.lock import SddLock, FileEntry, save_lock, sha256_file  # TASK-022
# hornero/cli.py: build_parser() uses argparse subparsers — add a nested
# 'sdd' group with its own sub-subparsers; read the current file first.
```

### Does NOT Exist
- ~~config key `sdd_upstream`~~ — you ADD it to config.py (`_TOP_KEYS` too)

## Acceptance Criteria

- [ ] **F2.5 gate**: fixture upstream ⇒ managed set + skeleton on disk; every lock hash verifies against both upstream and installed file; re-run leaves `git status --porcelain` empty (idempotent)
- [ ] Adoption: pre-existing identical file ⇒ current; edited file ⇒ kept + lock reflects local hash; `--force` ⇒ clobbered
- [ ] No `--from` and no config ⇒ exit non-zero with message, nothing written
- [ ] Full suite green; ruff + mypy clean

## Test Specification

```python
def test_f2_5_gate_install_and_idempotent_rerun(tmp_path): ...
def test_lock_hashes_verify(tmp_path): ...
def test_adopts_existing_identical_and_modified(tmp_path): ...
def test_force_overwrites(tmp_path): ...
def test_no_upstream_configured_refuses(tmp_path): ...
```

---

## Completion Note

**Completed by**: claude-fable-5 (session 0d52d2f9)
**Date**: 2026-07-06
**Notes**: hornero/sdd_toolkit/install.py + 'hornero sdd install' CLI group + config keys sdd_upstream/sdd_ref. Adoption semantics (identical=adopted, edited=kept-as-modified, --force clobbers), scaffold with .gitkeep, lock preserved verbatim when nothing moved (synced_at kept => idempotent). F2.5 GATE GREEN: fixture upstream => managed set + skeleton, lock hashes verify both ways, re-run leaves git status empty. Full suite 160 passed.

**Deviations from spec**: none

# TASK-026: `sdd status` / `sdd diff` / `sdd sync --pull` + hold/pin (F3.5 gate closer)

**Feature**: SPEC-002 — SDD toolkit: install, memory bootstrap, and cross-repo sync
**Spec**: `sdd/specs/SPEC-002-sdd-toolkit-sync.md`
**Status**: done
**Priority**: high
**Estimated effort**: M (2-4h)
**Depends-on**: TASK-025
**Assigned-to**: unassigned

---

## Context

SPEC-002 §7 CLI over the drift engine. G4: drift table one line per file.
**Closes the F3.5 phase gate**: the six-state fixture matrix resolves per
the §6 table and a diverged file blocks with exit code ≠ 0.

## Scope

- `hornero/sdd_toolkit/cli_sync.py` (thin; engine stays in drift.py):
  - `sdd status` — one line per managed file: state + path (+ policy);
    exit 0 (status never fails on drift, it reports).
  - `sdd diff [<file>]` — unified diff upstream vs local (stdlib difflib)
    for one file or all non-current files.
  - `sdd sync [--pull] [--dry-run] [--theirs <file>...] [--ours <file>...]
    [--force]` — pull is the default direction; `--dry-run` prints the
    action table and touches nothing; DIVERGED without an explicit
    `--theirs/--ours` for that file ⇒ **exit ≠ 0** listing the diverged
    files; `--theirs` copies upstream (lock updated), `--ours` keeps local
    and re-baselines the lock (`installed_hash = current`).
  - `sdd hold <file>` / `unhold <file>` / `pin <file>` — set lock policy.
  - Successful non-dry sync rewrites the lock (`synced_at`, commit).
- Wire into the `sdd` subparser group (TASK-023).
- Tests `tests/test_sdd_sync_cli.py` — **F3.5 gate**: fixture repo with all
  six states; `sync --pull` resolves per table; diverged blocks (exit ≠ 0);
  `--dry-run` leaves `git status --porcelain` unchanged.

**NOT in scope**: push/PR (TASK-027), workspace fanout (TASK-027).

## Codebase Contract (Anti-Hallucination)

```python
from hornero.sdd_toolkit.drift import DriftState, classify, apply_pull  # TASK-025
# cli.py 'sdd' group exists after TASK-023 — read it before extending.
# difflib.unified_diff for diff rendering; no external pager.
```

## Acceptance Criteria

- [ ] **F3.5 gate**: six-state matrix resolves per §6; diverged blocks with exit ≠ 0
- [ ] `--dry-run` mutates nothing (git-verified)
- [ ] `--theirs/--ours` resolve a diverged file explicitly; `--ours` re-baselines lock
- [ ] hold/pin round-trip via CLI and are respected by sync
- [ ] Full suite green; ruff + mypy clean

## Test Specification

```python
def test_f3_5_gate_matrix_resolution_and_diverged_blocks(tmp_path): ...
def test_dry_run_touches_nothing(tmp_path): ...
def test_theirs_ours_resolution(tmp_path): ...
def test_status_one_line_per_file(tmp_path): ...
def test_hold_pin_cli(tmp_path): ...
```

---

## Completion Note

**Completed by**: claude-fable-5
**Date**: 2026-07-08
**Notes**: hornero/sdd_toolkit/cli_sync.py (thin: engine stays in drift.py) + sdd subparser wiring. status = drift table + summary, exit 0 always. diff = difflib unified, upstream/ vs local/ labels, one file or all non-current. sync: dry-run prints the action table and writes nothing (git-verified); diverged without explicit resolution exits 1 listing the files while the REST of the table still resolves per §6; --theirs copies upstream + fast-forwards the lock; --ours keeps local and re-baselines BOTH legs (installed=current, upstream=now) so the file reads modified (push candidate) and a further upstream move re-diverges. hold/unhold/pin need no upstream. Upstream resolution: --from > lock.upstream (sync identity) > config. Prerequisite fix shipped first (9156c24): classify() now uses both lock legs so install()-adopted files read MODIFIED, never BEHIND — pull no longer clobbers kept files. F3.5 GATE GREEN: six-state fixture matrix resolves per the §6 table, diverged blocks with exit != 0, dry-run leaves porcelain empty. Suite 180 passed, ruff + mypy clean.

**Deviations from spec**: --ours re-baselines upstream_hash too (not only installed_hash) — required for the three-way model to read the resolution as modified instead of re-diverging; recorded with OQ9 in the spec Log.

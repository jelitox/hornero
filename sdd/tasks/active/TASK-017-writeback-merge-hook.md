# TASK-017: Write-back loop closure — merge→reindex hook + DUPLICATE detection (F4 gate closer)

**Feature**: SPEC-001 — Hornero: foundational contracts and MVP scope
**Spec**: `sdd/specs/SPEC-001-hornero-foundation.md`
**Status**: pending
**Priority**: medium
**Estimated effort**: L (4-8h)
**Depends-on**: TASK-012, TASK-014, TASK-016
**Assigned-to**: unassigned

---

## Context

F4 closes the loop (SPEC-001 §1 step 5): after a merge, the knowledge base is
reindexed so the next signal is reconciled against the **built** state — and
re-reconciling an already-covered signal yields `DUPLICATE`, not a new spec.
This task delivers the merge→reindex hook, the spec-patch-in-PR-branch
convention, OQ2's duplicate telemetry, and **closes the F4 phase gate**.

Phase: **F4 — Write-back** (gate closer).

---

## Scope

- **Merge→reindex hook** (§12 F4: "git hook or CI step" — ship both,
  install neither silently):
  - `hornero init --hooks` (new flag, default off) installs
    `.git/hooks/post-merge` calling `hornero reindex` (POSIX sh, check
    `hornero` on PATH, degrade to a warning). Installing a git hook mutates
    developer machines — keep it opt-in and idempotent.
  - Emit `docs/ci-reindex.example.yml` content via
    `hornero init --print-ci-hook` (stdout, user pastes into their CI) — no
    workflow files are written into target repos automatically.
- **Spec patch travels with the PR** (F4 deliverable "spec patch in PR
  branch"): extend `BuildBrief.description` rendering (TASK-014) so the
  brief instructs the coding agent to include the spec's `building→review`
  frontmatter update + refreshed reports in the same branch; for
  `MockBackend`, simulate by writing the transitioned spec copy into its log
  dir. Keep this a documented convention + mock simulation — hornero core
  still never pushes git refs.
- **DUPLICATE detection quality**: ensure the reconciler prompt (TASK-009)
  includes retrieved spec ids + titles + acceptance criteria so the LLM can
  classify DUPLICATE; with `FakeLLM` this is scripted — the REAL work here is
  the e2e fixture proving the pipeline records it.
- **OQ2 (leaning yes, F4)**: approved-and-applied runs `comment()` on the
  covering spec for each DUPLICATE delta: `"mentioned again in <signal-id>"`
  — signal-strength telemetry in the spec's Log.
- **F4 gate e2e** in `tests/test_writeback_e2e.py`: post-"merge" fixture —
  simulate merge by applying a NEW spec + running `reindex`; then re-run
  `reconcile` on the same signal (scripted FakeLLM keyed on the reindexed
  context) ⇒ delta set contains exactly one `DUPLICATE` for the covering
  spec, ledger records it, spec Log carries the OQ2 comment, no new spec
  file created.

**NOT in scope**: report regeneration in the build (TASK-019 wires the
post-build hook), GitHub Actions for THIS repo's CI.

---

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `hornero/hooks.py` | CREATE | post-merge hook install + CI snippet print |
| `hornero/cli.py` | MODIFY | `init --hooks` / `--print-ci-hook` flags |
| `hornero/adapters/dispatch.py` | MODIFY | brief convention + mock spec-copy simulation |
| `hornero/reconciler/run.py` | MODIFY | OQ2 duplicate comments on apply |
| `tests/test_writeback_e2e.py` | CREATE | F4 gate test |

---

## Codebase Contract (Anti-Hallucination)

> **CRITICAL**: verified against the repo on 2026-07-06. This task MODIFIES
> three modules written by earlier tasks — read their real code first; the
> names below are their task contracts, not gospel.

### Verified Imports
```python
from hornero.memory.reindex import reindex          # TASK-016
from hornero.reconciler.run import ...              # TASK-012 — read the file
from hornero.adapters.dispatch import brief_from_spec, MockBackend  # TASK-014
from hornero.models import DeltaKind                # TASK-002
```

### Existing Signatures to Use
```python
# RepoTracker.comment(ref, body) (TASK-006) — the OQ2 telemetry channel.
# DeltaKind.DUPLICATE semantics (TASK-002/§6): persisted, never presented for
# approval, never produces specs/briefs — the OQ2 comment happens at the
# APPLY stage of the run, not via HITL.
```

### Does NOT Exist
- ~~`pre-commit` framework~~ — not installed; the hook is a plain sh file
- ~~GitHub API usage~~ — none; "merge" in tests is simulated by filesystem
  state + reindex, exactly like the gate wording ("post-'merge' fixture")
- ~~automatic hook installation~~ — `init` without `--hooks` must NOT touch
  `.git/hooks/` (surprising mutation of developer machines is forbidden)

---

## Implementation Notes

### Key Constraints
- Hook script must be idempotent to install (marker comment; re-install
  replaces only hornero's block) and must not clobber an existing
  post-merge hook (append/refuse with message — refuse is acceptable MVP).
- DUPLICATE never blocks: even if `comment()` fails (missing covering spec),
  log to ledger and continue — telemetry must not break reconciliation.
- The F4 gate depends on reindex freshness: assert `status` reports `fresh`
  before the second reconcile in the e2e (catches ordering bugs).

### References in Codebase
- SPEC-001 §1 step 5, §12 F4 gate row, §14 OQ2, §13 R3; F4 deliverable list.

---

## Acceptance Criteria

- [ ] **F4 gate**: post-merge fixture → reindex → same-signal reconcile yields `DUPLICATE`; no new spec created
- [ ] DUPLICATE recorded in ledger + OQ2 comment on covering spec's Log
- [ ] `init --hooks` installs idempotent post-merge hook; plain `init` never touches `.git/hooks/`
- [ ] `--print-ci-hook` emits a valid YAML snippet to stdout
- [ ] Full suite green: `pytest -q`; `ruff check` + `mypy hornero` clean

---

## Test Specification

```python
# tests/test_writeback_e2e.py
def test_f4_gate_reindex_then_duplicate(tmp_path): ...
def test_duplicate_comment_on_covering_spec(tmp_path): ...
def test_duplicate_never_creates_spec_or_brief(tmp_path): ...
def test_hook_install_optin_and_idempotent(tmp_path): ...
def test_existing_foreign_hook_not_clobbered(tmp_path): ...
```

---

## Agent Instructions

When you pick up this task:

1. **Read the spec** at the path listed above for full context
2. **Check dependencies** — verify TASK-012, TASK-014, TASK-016 are in `sdd/tasks/completed/` (F2/F3 gates green)
3. **Verify the Codebase Contract** — before writing ANY code; you are modifying other tasks' modules
4. **Update status** in `sdd/tasks/index/hornero-foundation.json` → `"in-progress"`
5. **Implement** following the scope, codebase contract, and notes above
6. **Verify** all acceptance criteria are met
7. **Move this file** to `sdd/tasks/completed/TASK-017-writeback-merge-hook.md`
8. **Update index** → `"done"`
9. **Fill in the Completion Note** below

---

## Completion Note

*(Agent fills this in when done)*

**Completed by**:
**Date**:
**Notes**:

**Deviations from spec**: none

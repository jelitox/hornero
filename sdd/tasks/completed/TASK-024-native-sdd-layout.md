# TASK-024: §2 amendment — hornero adopts the SDD layout as native spec store

**Feature**: SPEC-002 — SDD toolkit: install, memory bootstrap, and cross-repo sync
**Spec**: `sdd/specs/SPEC-002-sdd-toolkit-sync.md`
**Status**: done
**Priority**: high
**Estimated effort**: L (4-8h)
**Depends-on**: TASK-023
**Assigned-to**: unassigned

---

## Context

SPEC-002 §2 amends SPEC-001 §4: `product/specs` and `product/decisions` are
dropped. Specs live in `sdd/specs/`, ADRs in `sdd/decisions/`, reports in
`sdd/reports/`; low-confidence NEW deltas become brainstorm proposals in
`sdd/proposals/`; the knowledge layer indexes the full `sdd/` corpus. §8:
`hornero init` runs `sdd install` as its final step (`--no-sdd` skips);
traceability gains an SDD-task-ids column.

## Scope

- **Path migration** (update every consumer + its tests):
  - specs dir: `product/specs` → `sdd/specs`; decisions → `sdd/decisions`;
    reports → `sdd/reports` (`cli.py`, `reconciler/run.py`, `build.py`,
    `reports/engine.py` consumers).
  - `hornero init` scaffolds `sdd/{proposals,specs,state,tasks/active,
    tasks/completed,tasks/index,reviews,decisions,reports}/` (+`.hornero/`)
    and runs `sdd install` last when an upstream is configured
    (config `sdd_upstream` or `--from`); `--no-sdd` (and no upstream) skips
    with a hint. Init stays offline-safe by default.
  - `SpecCorpus` glob accepts BOTH `SPEC-*.md` and `*.spec.md` (OQ8: ids
    stay `SPEC-NNN`, filenames keep this repo's `SPEC-NNN-<slug>.md`).
  - `knowledge_roots` → `sdd/` + `.hornero/processed/` (findings under
    `sdd/state/*/findings/` ride along for free).
- **Reconciler routing** (§2): NEW delta whose `proposed_patch` parses as a
  valid spec ⇒ `sdd/specs/SPEC-NNN-<slug>.md` (as today). Otherwise ⇒
  brainstorm proposal `sdd/proposals/<slug>.brainstorm.md` rendered from
  `sdd/templates/brainstorm.md` when present (else a minimal inline
  template), recorded in the ApplyReport as `proposals`.
- **Traceability**: add an "SDD tasks" column reading
  `sdd/tasks/index/*.json` (tasks whose `spec` field references the spec's
  file, or whose `feature_id` equals the spec id).
- Update ALL affected tests (`test_cli`, `test_apply`, `test_reconcile_e2e`,
  `test_build_e2e`, `test_reindex`, `test_reports_*`, `test_writeback_e2e`).

**NOT in scope**: dispatch payloads invoking /sdd-task machinery (that is
the existing brief write-back contract; deeper SDD-dispatch integration is
post-MVP), drift engine.

## Codebase Contract (Anti-Hallucination)

```python
# Read the CURRENT code before editing — every path below exists today and
# is verified: hornero/cli.py (_PRODUCT_DIRS), reconciler/run.py + apply.py
# (product/specs, product/decisions), build.py, reports/engine.py
# (build_context), memory/knowledge.py (knowledge_roots), and their tests.
# The invalid-NEW-patch behavior changes: it becomes a PROPOSAL, no longer
# an error — update test_apply.test_invalid_new_patch_leaves_no_file.
```

### Does NOT Exist
- ~~`product/` in the post-amendment layout~~ — remove it from init; do NOT
  migrate existing repos automatically (none exist besides fixtures)

## Acceptance Criteria

- [ ] `hornero init && hornero status` exit 0; scaffolds the sdd layout, no `product/`
- [ ] Reconcile e2e (F2 gate) green against `sdd/specs`
- [ ] NEW delta with non-spec patch ⇒ `sdd/proposals/<slug>.brainstorm.md`, signal acked, no error
- [ ] Traceability shows task ids for a spec present in `sdd/tasks/index/`
- [ ] Full suite green; ruff + mypy clean

## Test Specification

```python
def test_init_scaffolds_sdd_layout(...): ...
def test_new_delta_prose_patch_becomes_proposal(...): ...
def test_traceability_sdd_task_column(...): ...
# plus mechanical path updates across the existing suites
```

---

## Completion Note

**Completed by**: claude-fable-5
**Date**: 2026-07-07
**Notes**: New hornero/layout.py is the single path resolver (sdd/specs, sdd/decisions, sdd/reports, sdd/proposals, sdd/templates, sdd/tasks/index). init scaffolds the full SDD skeleton via scaffold_dirs (no product/), runs sdd install last only when sdd_upstream is configured (offline-safe), --no-sdd skips with no hint. SpecCorpus loads both SPEC-*.md and *.spec.md (OQ8). knowledge_roots => sdd/ + .hornero/processed/. Invalid NEW patch now routes to sdd/proposals/<slug>.brainstorm.md (repo brainstorm template header when present), recorded in ApplyReport.proposals, signal still acked — no longer an error. Traceability gains an "SDD tasks" column matching by feature_id OR per-task spec-file reference; a broken index JSON never breaks the report. All suites migrated to the sdd/ layout. Gates: init+status exit 0, F2 reconcile e2e green, full suite 163 passed, ruff + mypy clean.

**Deviations from spec**: none

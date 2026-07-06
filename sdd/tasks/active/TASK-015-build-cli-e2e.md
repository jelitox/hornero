# TASK-015: `hornero build` — approved specs → briefs → dispatch → status transitions (F3 gate closer)

**Feature**: SPEC-001 — Hornero: foundational contracts and MVP scope
**Spec**: `sdd/specs/SPEC-001-hornero-foundation.md`
**Status**: pending
**Priority**: medium
**Estimated effort**: M (2-4h)
**Depends-on**: TASK-004, TASK-006, TASK-007, TASK-014
**Assigned-to**: unassigned

---

## Context

SPEC-001 §10: `hornero build [SPEC-ID ...]` turns approved specs into briefs
and drives them through the `DispatchPort`, transitioning
`approved → building → review` (or `→ needs_human` on failure, §5 diagram)
via the tracker. NG3: no autonomous dispatch — `build` without an approved
spec is a **no-op**. This task **closes the F3 phase gate**.

Phase: **F3 — Dispatch bridge** (gate closer).

---

## Scope

- Replace the `build` stub in `hornero/cli.py` with `hornero/build.py`:
  - Args: zero or more SPEC-IDs; none given ⇒ all `status: approved` specs.
    Explicit id that is not approved ⇒ non-zero exit listing offending ids,
    dispatch NOTHING (all-or-nothing per invocation, conservative).
    No approved specs at all ⇒ print "nothing to build", **exit 0** (no-op,
    NG3 — a quiet no-op is the contract).
  - Per spec: `tracker.transition(ref, "building")` + Log comment →
    `brief_from_spec` → `dispatch.dispatch(brief)` →
    - `completed` ⇒ `transition("review")`, comment with `pr_url`,
      `ledger.record_dispatch(..., pr_url=...)`.
    - `failed` / `needs_human` ⇒ `transition("needs_human")`, comment with
      `log_path`, ledger row.
  - Backend selection: `--backend {cli,mock}` CLI flag overrides config
    `dispatch.backend_order` (§10 shows exactly these two choices; `api` is
    config-only — deliberately NOT a CLI choice, invariant 3).
  - Final step placeholder: after a successful dispatch batch, call a
    `post_build_hooks` list (empty for now — TASK-019 appends report
    regeneration; keep the seam explicit so F5 wires in cleanly).
- **F3 gate e2e** in `tests/test_build_e2e.py`: fixture repo with one
  approved spec → `hornero build --backend mock` → frontmatter shows the
  spec transitioned `approved→building→review` (assert both Log lines and
  final status), fake PR URL present in the ledger `dispatches` table.

**NOT in scope**: report generation (TASK-018/019), merge/write-back hooks
(TASK-017), spec-patch-in-PR-branch (TASK-017).

---

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `hornero/build.py` | CREATE | build command implementation |
| `hornero/cli.py` | MODIFY | wire real `build` + `--backend` flag |
| `tests/test_build_e2e.py` | CREATE | F3 gate test |

---

## Codebase Contract (Anti-Hallucination)

> **CRITICAL**: verified against the repo on 2026-07-06. Re-verify dependency
> tasks' real signatures on pickup.

### Verified Imports
```python
from hornero.adapters.dispatch import MulticodersDispatch, brief_from_spec  # TASK-014
from hornero.adapters.repo_tracker import RepoTracker    # TASK-006
from hornero.lifecycle import SpecCorpus, Status         # TASK-003
from hornero.memory.ledger import Ledger                 # TASK-004
from hornero.config import load_config                   # TASK-007
```

### Existing Signatures to Use
```python
# hornero/lifecycle.py (TASK-003) TRANSITIONS: approved→building→{review,needs_human}
# hornero/adapters/dispatch.py (TASK-014): dispatch() returns BuildResult,
#   never raises for operational failures.
```

### Does NOT Exist
- ~~`--backend api` CLI choice~~ — deliberately excluded; config-only opt-in
- ~~parallel dispatch / job queue~~ — MVP is sequential, one spec at a time
- ~~git push / PR creation~~ — the backend simulates it (mock) or owns it
  (cli); hornero core performs no git network operations

---

## Implementation Notes

### Key Constraints
- Transition BEFORE dispatch (building) and AFTER (review/needs_human) so a
  crash mid-dispatch leaves an honest `building` state a human can see in
  `hornero status`.
- All-or-nothing validation of explicit ids happens before ANY transition.
- Every state change goes through `RepoTracker` (auditable Log lines), never
  by writing frontmatter directly from this module.
- Determinism: mock backend + injected clock ⇒ byte-stable fixture diffs.

### References in Codebase
- SPEC-001 §5 (machine), §10 (CLI), §12 F3 gate row, NG3; CLAUDE.md
  invariant 3.

---

## Acceptance Criteria

- [ ] **F3 gate**: approved fixture spec + mock backend ⇒ status history `approved→building→review`, fake PR URL in ledger
- [ ] `build` with no approved specs: no-op, exit 0, no transitions
- [ ] Explicit non-approved id: non-zero exit, zero transitions
- [ ] Failed dispatch ⇒ `needs_human` + log path in spec Log + ledger row
- [ ] Full suite green: `pytest -q`; `ruff check` + `mypy hornero` clean

---

## Test Specification

```python
# tests/test_build_e2e.py
from hornero.cli import main


def test_f3_gate_approved_to_review_with_fake_pr(tmp_path): ...
def test_no_approved_specs_is_noop_exit_zero(tmp_path): ...
def test_explicit_unapproved_id_rejected_all_or_nothing(tmp_path): ...
def test_failed_dispatch_goes_needs_human(tmp_path): ...
```

---

## Agent Instructions

When you pick up this task:

1. **Read the spec** at the path listed above for full context
2. **Check dependencies** — verify TASK-004, TASK-006, TASK-007, TASK-014 are in `sdd/tasks/completed/` (and that the F2 gate is green — do not close F3 over a red F2)
3. **Verify the Codebase Contract** — before writing ANY code
4. **Update status** in `sdd/tasks/index/hornero-foundation.json` → `"in-progress"`
5. **Implement** following the scope, codebase contract, and notes above
6. **Verify** all acceptance criteria are met
7. **Move this file** to `sdd/tasks/completed/TASK-015-build-cli-e2e.md`
8. **Update index** → `"done"`
9. **Fill in the Completion Note** below

---

## Completion Note

*(Agent fills this in when done)*

**Completed by**:
**Date**:
**Notes**:

**Deviations from spec**: none

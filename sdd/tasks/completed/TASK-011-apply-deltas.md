# TASK-011: Apply step — approved deltas → spec files + ADRs + signal ack

**Feature**: SPEC-001 — Hornero: foundational contracts and MVP scope
**Spec**: `sdd/specs/SPEC-001-hornero-foundation.md`
**Status**: done
**Priority**: high
**Estimated effort**: L (4-8h)
**Depends-on**: TASK-002, TASK-003, TASK-005, TASK-006
**Assigned-to**: unassigned

---

## Context

SPEC-001 §9 step 5: approved deltas write/patch spec files under
`product/specs/`, append an ADR when a delta reverses a prior decision, and
`ack()` the signal. Hard invariant (§6): **no delta mutates `product/specs/`
before `status == "approved"`** — this module is the only writer and it
checks that guard itself (defense in depth over the HITL gate).

Phase: **F2 — Reconciler**.

---

## Scope

- Implement `hornero/reconciler/apply.py`:
  - `apply_deltas(reviewed: list[ReviewedDelta], corpus: SpecCorpus, tracker: TrackerPort, source: SignalSource, decisions_dir: Path, clock) -> ApplyReport`
  - Per approved delta, by kind:
    - `NEW` — allocate `corpus.next_spec_id()`, write
      `product/specs/SPEC-NNN-<slug>.md` from `proposed_patch` (full body).
      Ensure frontmatter is valid per TASK-003 (`parse_spec` the result;
      invalid ⇒ abort that delta with an error entry, write nothing).
      Set `sources:` to the delta's evidence signal ids. Status starts
      `proposed`? **No** — the human already approved the delta, so the new
      spec is born `proposed` per the §5 machine and immediately transitioned
      to `approved` via the tracker (two auditable steps, one Log line each).
    - `CHANGED` — apply the unified diff in `proposed_patch` to the affected
      spec(s). Implement a minimal unified-diff applier (stdlib only — no
      `patch` binary, no git dependency): context lines must match exactly or
      the delta fails with an error entry (never fuzzy-apply). Update
      `sources:` (append new signal ids).
    - `OBSOLETE` — transition affected specs to `obsolete` via the tracker,
      `comment()` why (with signal id).
    - `DUPLICATE` / rejected / skipped — **never touch product/**; report only.
  - ADR writing: when a delta OBSOLETEs or CHANGEs a spec that an existing
    ADR/decision supported (MVP heuristic: the delta's `affected_specs`
    appear in any `product/decisions/ADR-*.md`), append
    `product/decisions/ADR-NNN-<slug>.md` (monotonic ids, §4) recording:
    what reversed, evidence, date. Keep the template minimal and inline.
  - `ack` each signal only after ALL its approved deltas applied cleanly.
  - `ApplyReport` dataclass: created/patched/obsoleted/errors lists — the
    CLI (TASK-012) renders it and the ledger records it.
- Tests in `tests/test_apply.py` on `tmp_path` fixture repos.

**NOT in scope**: HITL prompting (TASK-010), ledger writes (TASK-012
orchestrates), git commits/branches (F4), reindexing (TASK-016).

---

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `hornero/reconciler/apply.py` | CREATE | apply_deltas + diff applier + ADR writer |
| `tests/test_apply.py` | CREATE | per-kind apply, guard, ack-ordering tests |

---

## Codebase Contract (Anti-Hallucination)

> **CRITICAL**: verified against the repo on 2026-07-06. Re-verify dependency
> tasks' real signatures on pickup.

### Verified Imports
```python
from hornero.models import DeltaKind, RequirementDelta        # TASK-002
from hornero.lifecycle import SpecCorpus, parse_spec           # TASK-003
from hornero.ports import SignalSource, TrackerPort            # TASK-001
from hornero.reconciler.hitl import ReviewedDelta, Decision    # TASK-010 — if not
# yet completed, define the minimal shape here and reconcile when it lands
```

### Existing Signatures to Use
```python
# hornero/adapters/repo_tracker.py (TASK-006): transition edits only the
# status line; comment appends to '## Log'. Illegal transitions RAISE.
# hornero/adapters/inbox.py (TASK-005): ack(signal_id) idempotent.
```

### Does NOT Exist
- ~~`unidiff`, `patch-ng`, `whatthepatch`~~ — NOT installed; write the
  applier by hand (exact-context, fail-hard)
- ~~`git apply` shelling-out~~ — forbidden here; pure-filesystem apply keeps
  `--dry-run` and tests hermetic
- ~~a `## Decision reversal detector` in lifecycle~~ — the ADR heuristic
  lives HERE, nothing else provides it

---

## Implementation Notes

### Key Constraints
- **Guard first**: any delta whose review decision is not APPROVED (or
  EDITED-then-approved) contributes zero filesystem writes — assert this in
  tests by hashing the tree before/after.
- Exact-match diff application: a context mismatch is an *error outcome*
  (delta marked failed in the report), never a partial write — write to a
  temp file and rename, or apply in memory and write once.
- EDITED deltas apply the **edited** patch (from `ReviewResult.patch`).
- Monotonic ADR ids scan `product/decisions/` (same rule as spec ids §4).
- All paths/clock injected — no `datetime.now()` inside logic (invariant 6).

### References in Codebase
- SPEC-001 §4 (layout, monotonic ids), §5 (born-proposed machine), §6 (guard
  invariant), §9 step 5; CLAUDE.md invariant 2 (fail-closed philosophy).

---

## Acceptance Criteria

- [ ] NEW delta produces a parseable spec file with allocated id + sources, transitioned to `approved` with Log entries
- [ ] CHANGED delta with exact context applies; with stale context fails that delta, file untouched
- [ ] OBSOLETE delta transitions spec + writes ADR when the heuristic fires
- [ ] Non-approved deltas: repo tree hash unchanged
- [ ] Signal acked only when all its approved deltas applied cleanly
- [ ] All tests pass: `pytest tests/test_apply.py -q`; `ruff check` + `mypy hornero` clean

---

## Test Specification

```python
# tests/test_apply.py
from hornero.reconciler.apply import apply_deltas


def test_new_delta_creates_valid_spec(tmp_path): ...
def test_changed_delta_applies_exact_diff(tmp_path): ...
def test_changed_delta_stale_context_fails_cleanly(tmp_path): ...
def test_obsolete_transitions_and_writes_adr(tmp_path): ...
def test_unapproved_deltas_write_nothing(tmp_path): ...
def test_ack_only_after_clean_apply(tmp_path): ...
```

---

## Agent Instructions

When you pick up this task:

1. **Read the spec** at the path listed above for full context
2. **Check dependencies** — verify TASK-002, TASK-003, TASK-005, TASK-006 are in `sdd/tasks/completed/`
3. **Verify the Codebase Contract** — before writing ANY code
4. **Update status** in `sdd/tasks/index/hornero-foundation.json` → `"in-progress"`
5. **Implement** following the scope, codebase contract, and notes above
6. **Verify** all acceptance criteria are met
7. **Move this file** to `sdd/tasks/completed/TASK-011-apply-deltas.md`
8. **Update index** → `"done"`
9. **Fill in the Completion Note** below

---

## Completion Note

**Completed by**: claude-fable-5 (session 0d52d2f9)
**Date**: 2026-07-06
**Notes**: hornero/reconciler/apply.py: exact-context unified diff applier (fail-hard), NEW (id allocation, spec/status/sources rewrite, parse-validate-or-unlink, born proposed then approved with Log entries), CHANGED (diff + source merge + comment), OBSOLETE (transition + comment), ADR writer with mention heuristic, ack only after clean apply of all decided deltas. 10 tests green.

**Deviations from spec**: ack policy refined: a signal whose deltas were all human-REJECTED is acked too (decision made, ledger keeps the audit); pure-SKIPPED signals stay in the inbox (fail-closed).

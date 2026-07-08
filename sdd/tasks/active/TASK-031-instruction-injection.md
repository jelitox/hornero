# TASK-031: CLAUDE.md/AGENTS.md standardized section injection (F7)

**Feature**: SPEC-003 — Hornero wiki — agent-facing living docs, git watermarks, and code-as-signal
**Spec**: `sdd/specs/SPEC-003-wiki-watermarks-gitsignal.md`
**Status**: pending
**Priority**: medium
**Estimated effort**: S
**Depends-on**: TASK-028
**Assigned-to**: unassigned

---

## Scope

SPEC-003 §8. `hornero/instructions.py`: stable `## Hornero` section (exact
template); top-level CLAUDE.md/AGENTS.md only; create AGENTS.md with just the
section when neither exists; refresh only when missing or SEMANTICALLY stale
(whitespace-normalized comparison), preserving surrounding content. Wired as a
final step of `hornero init` and `hornero sdd install`. Gate: re-running
injection on a current file leaves `git diff` empty.

## Acceptance Criteria

- [ ] Phase gate assertions from the spec table pass verbatim
- [ ] Full suite green; ruff + mypy clean

---

## Completion Note

*(Agent fills this in when done)*

**Completed by**:
**Date**:
**Notes**:

**Deviations from spec**: none

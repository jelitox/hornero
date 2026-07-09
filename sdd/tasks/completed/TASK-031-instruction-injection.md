# TASK-031: CLAUDE.md/AGENTS.md standardized section injection (F7)

**Feature**: SPEC-003 — Hornero wiki — agent-facing living docs, git watermarks, and code-as-signal
**Spec**: `sdd/specs/SPEC-003-wiki-watermarks-gitsignal.md`
**Status**: done
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

**Completed by**: claude-fable-5
**Date**: 2026-07-08
**Notes**: hornero/instructions.py — stable '## Hornero' section (spec-exact template); injects into existing top-level CLAUDE.md/AGENTS.md (creates AGENTS.md with just the section when neither exists); replacement bounded by the next '## ' heading, neighbors preserved; staleness is SEMANTIC (whitespace-normalized comparison — reflow never rewrites). Wired as a final step of hornero init and sdd install. Idempotency gate green (rerun leaves git diff empty). Suite 212 passed. F7 gate fully closed (with TASK-030).

**Deviations from spec**: none

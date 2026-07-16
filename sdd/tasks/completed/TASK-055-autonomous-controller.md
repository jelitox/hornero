# TASK-055: Run a bounded autonomous improvement loop
**Feature**: SPEC-005 | **Status**: done | **Priority**: critical | **Depends-on**: TASK-041, TASK-043, TASK-050, TASK-052, TASK-053, TASK-054

## Scope
Add `hornero improve scan|plan|run|status`; prioritize findings, enforce budgets/risk policies/HITL, execute in isolation, verify gates, roll back failures, and record learning in ledger/graph/progress.
## Acceptance Criteria
- [x] Low-risk fake improvement completes through verify-and-learn
- [x] Risky/destructive/billed work cannot run without explicit approval

## Completion Note
Implemented scan/plan/run/status, default-off budgets and risk policy, exact
medium/high approval, isolated worktrees, gates, rollback, review branches,
ledger outcomes and finding-to-run graph learning.

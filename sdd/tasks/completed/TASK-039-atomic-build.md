# TASK-039: Make build lifecycle atomic and recoverable
**Feature**: SPEC-005 | **Status**: done | **Priority**: high | **Depends-on**: none

## Scope
Validate all briefs before transitions; catch operational exceptions; close ledger runs and move failed specs to truthful states with traces/comments.
## Acceptance Criteria
- [ ] Invalid criteria cause zero misleading building states
- [ ] Every started build run reaches a terminal ledger outcome

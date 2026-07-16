# TASK-041: Persist truthful reconciliation outcomes
**Feature**: SPEC-005 | **Status**: done | **Priority**: high | **Depends-on**: TASK-040

## Scope
Distinguish human decision from apply result, persist failed/created/patched outcomes, and keep signal acknowledgement aligned with effective writes.
## Acceptance Criteria
- [ ] Failed applies are never recorded as successfully applied
- [ ] Traceability reports expose decision and outcome separately

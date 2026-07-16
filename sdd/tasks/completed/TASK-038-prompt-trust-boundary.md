# TASK-038: Add prompt trust boundaries
**Feature**: SPEC-005 | **Status**: done | **Priority**: high | **Depends-on**: TASK-037

## Scope
Delimit untrusted signal/context blocks, state non-instruction policy, constrain output schema and patches, and log rejected prompt-risk content.
## Acceptance Criteria
- [ ] Injection fixtures cannot override system constraints
- [ ] Existing verbatim-evidence invariant remains green

# TASK-044: Discover and validate repository roots
**Feature**: SPEC-005 | **Status**: done | **Priority**: high | **Depends-on**: none

## Scope
Find the nearest parent with `.hornero` or git metadata for operational commands; keep init/new destination semantics explicit and prevent nested accidental state.
## Acceptance Criteria
- [ ] Commands from nested directories operate on the intended root
- [ ] Ambiguous/missing roots fail with actionable errors

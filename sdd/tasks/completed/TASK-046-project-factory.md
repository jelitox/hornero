# TASK-046: Create repositories from Hornero
**Feature**: SPEC-005 | **Status**: done | **Priority**: high | **Depends-on**: TASK-036, TASK-042, TASK-044

## Scope
Add `hornero new` with destination validation, git init, Hornero/SDD bootstrap, blueprint selection, optional initial commit, and transactional cleanup.
## Acceptance Criteria
- [x] New fixture project is initialized and passes its smoke gate
- [x] Existing/non-empty destinations are never clobbered

## Completion Note
Implemented transactional `hornero new`, Git/bootstrap options, safe destinations,
and smoke-tested built-in projects in `tests/test_blueprints.py`.

# TASK-036: Enforce repository path containment
**Feature**: SPEC-005 | **Status**: done | **Priority**: critical | **Depends-on**: none

## Scope
Centralize validation for manifest, lock, blueprint, sync, policy, diff, and push paths. Reject absolute, empty, traversal, symlink-escape, and non-contained destinations before any write.
## Acceptance Criteria
- [ ] Malicious managed/scaffold/lock/CLI paths cannot write outside roots
- [ ] Focused tests and full quality gates pass

# TASK-040: Allocate concurrent-safe run identifiers
**Feature**: SPEC-005 | **Status**: done | **Priority**: high | **Depends-on**: none

## Scope
Replace COUNT-based IDs with an atomic SQLite allocation and add schema migration plus concurrent-connection tests.
## Acceptance Criteria
- [ ] Parallel allocations are unique and monotonic
- [ ] Existing ledgers migrate without losing records

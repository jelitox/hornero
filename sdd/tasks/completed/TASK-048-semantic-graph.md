# TASK-048: Build the semantic project graph
**Feature**: SPEC-005 | **Status**: done | **Priority**: high | **Depends-on**: TASK-037, TASK-045

## Scope
Add typed entities/relations for requirements, criteria, decisions, tasks, code symbols, tests, controls, risks, findings, and runs while retaining file pages.
## Acceptance Criteria
- [x] End-to-end fixture supports source-to-control traversal
- [x] Graph output is deterministic and queryable offline

## Completion Note
SQLite schema 2 now projects requirements, sources, criteria, controls, tasks,
decisions, symbols, tests, findings and ledger runs with typed relations.

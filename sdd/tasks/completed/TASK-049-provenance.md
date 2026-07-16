# TASK-049: Add graph provenance and history
**Feature**: SPEC-005 | **Status**: done | **Priority**: high | **Depends-on**: TASK-048

## Scope
Persist source URI/hash, origin kind, generator/model, confidence, validity, timestamps/commit, evidence locators, and supersession for nodes and edges.
## Acceptance Criteria
- [x] Every semantic record has valid provenance
- [x] Changed sources retain auditable lineage

## Completion Note
Every current entity/relation has source path/hash, origin, generator,
confidence and locator. Git-backed primary records and append-only ledger runs
retain history while the deterministic graph remains rebuildable derived state.

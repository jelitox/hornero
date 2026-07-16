# TASK-045: Validate and recover derived indexes
**Feature**: SPEC-005 | **Status**: done | **Priority**: high | **Depends-on**: TASK-037, TASK-044

## Scope
Detect corrupt manifest/SQLite/schema, quarantine derived artifacts, rebuild atomically, and expose health without traceback.
## Acceptance Criteria
- [ ] Corrupt derived state is diagnosed and safely rebuilt
- [ ] Primary-record corruption still fails closed

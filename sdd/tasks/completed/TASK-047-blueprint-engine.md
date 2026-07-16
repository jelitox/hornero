# TASK-047: Build composable versioned blueprints
**Feature**: SPEC-005 | **Status**: done | **Priority**: high | **Depends-on**: TASK-046

## Scope
Define blueprint manifests, typed variables, components/overlays, safe rendering, lockfile hashes, inventory, status, and upgrade drift.
## Acceptance Criteria
- [x] Built-in stacks render deterministically and compose cleanly
- [x] Local edits are detected and never silently overwritten

## Completion Note
Added typed built-in components/blueprints, allowlisted rendering,
`.hornero/blueprint.lock`, inventory and hash-based drift status.

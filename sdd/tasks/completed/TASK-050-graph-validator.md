# TASK-050: Validate graph and traceability on invocation
**Feature**: SPEC-005 | **Status**: done | **Priority**: critical | **Depends-on**: TASK-049

## Scope
Add `hornero validate`, validator APIs, preflight integration, health severities, dangling/stale/contradiction/secret/coverage rules, and repair mode for derived state.
## Acceptance Criteria
- [x] Blocking graph defects return non-zero before decisions execute
- [x] JSON and human reports carry stable finding IDs

## Completion Note
Added `validate [--repair]`, stable IDs, graph/provenance/secret/coverage rules,
quarantine/rebuild, and non-mutating decision preflights for reconcile/build.

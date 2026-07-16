# TASK-042: Validate configuration types and values
**Feature**: SPEC-005 | **Status**: done | **Priority**: high | **Depends-on**: none

## Scope
Reject wrong scalar/container types, empty critical values, invalid provider/backend/policy values, duplicate sources, and unsafe command argv configuration.
## Acceptance Criteria
- [ ] Invalid YAML shapes fail closed with field-specific errors
- [ ] Defaults and current valid configurations remain compatible

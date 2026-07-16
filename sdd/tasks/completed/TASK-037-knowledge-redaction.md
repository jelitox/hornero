# TASK-037: Redact and classify knowledge inputs
**Feature**: SPEC-005 | **Status**: done | **Priority**: critical | **Depends-on**: TASK-036

## Scope
Redact secrets before fallback/SQLite persistence, classify trust, retain source hashes, and exclude known credential files without leaking values into reports or retrieval.
## Acceptance Criteria
- [ ] Planted secrets are absent from every derived knowledge artifact
- [ ] Redaction remains deterministic and traceable

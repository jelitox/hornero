# TASK-035: DR retrieval surfacing + wiki decision links (F11 gate closer)

**Feature**: SPEC-004 — Flight recorder & scribe — capturing, distilling, and auditing agent decisions
**Spec**: `sdd/specs/SPEC-004-flight-recorder-scribe.md`
**Status**: pending
**Priority**: medium
**Estimated effort**: M
**Depends-on**: TASK-030, TASK-034
**Assigned-to**: unassigned

---

## Scope

SPEC-004 §5, §4.3. Reconciler research: for each drafted delta, retrieve
from the knowledge layer; hits under sdd/decisions/DR-*.md surface as a
"[memory] DR-NNN ..." note prepended to the HITL preview (channel protocol
unchanged). Wiki: quickstart links sdd/decisions/ as the decision-history
entrypoint (mechanically ensured); updater prompt gains DR-linking guidance
(W5 promotion cites the DR). Gate F11: fixture where a signal re-proposes a
DR-rejected approach -> the delta preview includes the DR reference.

## Acceptance Criteria

- [ ] Phase gate assertions from the spec table pass verbatim
- [ ] Full suite green; ruff + mypy clean

---

## Completion Note

*(Agent fills this in when done)*

**Completed by**:
**Date**:
**Notes**:

**Deviations from spec**: none

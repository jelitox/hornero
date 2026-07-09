# TASK-035: DR retrieval surfacing + wiki decision links (F11 gate closer)

**Feature**: SPEC-004 — Flight recorder & scribe — capturing, distilling, and auditing agent decisions
**Spec**: `sdd/specs/SPEC-004-flight-recorder-scribe.md`
**Status**: done
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

**Completed by**: claude-fable-5
**Date**: 2026-07-08
**Notes**: knowledge._kind_of classifies DR-*.md as decisions; gate() gains optional per-delta annotations prepended to the HITL preview (channel protocol unchanged); run_reconcile retrieves per delta and surfaces up to 2 DR hits as '[memory] DR-NNN...' lines BEFORE the patch. Wiki: quickstart mechanically gains a Decision history section linking sdd/decisions/ when the model omits it; updater prompt instructs DR-linking + cite-not-restate. F11 GATE GREEN: a signal re-proposing a DR-rejected approach shows the DR in the preview. Suite 234 passed. SPEC-004 scope closes with this task.

**Deviations from spec**: none

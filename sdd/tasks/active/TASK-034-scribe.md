# TASK-034: Scribe: trace -> Decision Record with verified citations (F10 gate closer)

**Feature**: SPEC-004 — Flight recorder & scribe — capturing, distilling, and auditing agent decisions
**Spec**: `sdd/specs/SPEC-004-flight-recorder-scribe.md`
**Status**: pending
**Priority**: high
**Estimated effort**: L
**Depends-on**: TASK-033
**Assigned-to**: unassigned

---

## Scope

SPEC-004 §4. `sdd/templates/decision_record.md`; `hornero/scribe.py`:
input = trace + spec ONLY (S2); LLM (models.scribe, FakeLLM-tested) returns
STRICT JSON sections whose every claim carries [e#N-e#M]; mechanical citation
verifier: range must resolve to real events AND include >=1 action event
(S3) — unanchorable claims are DROPPED and ledger-logged, never kept;
trivial trace (no actions) => no DR, "no decision content" logged (S4);
DR-NNN numbering in sdd/decisions/, written through redact(). Auto-run at
dispatch close when models.scribe resolves (hint otherwise); `hornero scribe
<run_ref> [--force]` for adopted/historical traces. Gate F10: fixture trace
-> DR with all citations mechanically verified; unanchorable-claim fixture ->
dropped + logged; trivial-run fixture -> no DR.

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

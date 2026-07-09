# TASK-033: Trace envelope + recorder + runs CLI (F9 gate closer)

**Feature**: SPEC-004 — Flight recorder & scribe — capturing, distilling, and auditing agent decisions
**Spec**: `sdd/specs/SPEC-004-flight-recorder-scribe.md`
**Status**: done
**Priority**: high
**Estimated effort**: L
**Depends-on**: TASK-029
**Assigned-to**: unassigned

---

## Scope

SPEC-004 §3, §6. `hornero/flight.py`: TraceEvent envelope (seq, ts,
run_id, actor, kind enum, summary, payload) with redaction AT WRITE; 
TraceWriter appends `.hornero/runs/<run_ref>/trace.jsonl` (zstd feature-
detected on close, else plain); tolerant Claude Code transcript adopter.
`MulticodersDispatch.dispatch(brief, run_ref)` MUST produce a trace —
MockBackend emits a synthetic run.started/message/tool_use/tool_result/
run.finished stream; BuildResult.log_path re-specified as trace_path
(schema + all consumers updated). Ledger gains `agent_runs` (run_ref,
spec_id, task_id, actor, status, trace_path, started/finished) and the
traceability report a "runs" column. CLI: `hornero runs list [--spec]`,
`runs show <ref> [--kind a,b] [--range e#N:e#M]`, `runs adopt <jsonl>`,
`runs prune --keep-days N`. Gate F9: mock dispatch produces a complete
ordered trace; planted secrets absent from trace bytes; show --range
returns exact slices; adopt registers a fixture transcript.

## Acceptance Criteria

- [ ] Phase gate assertions from the spec table pass verbatim
- [ ] Full suite green; ruff + mypy clean

---

## Completion Note

**Completed by**: claude-fable-5
**Date**: 2026-07-08
**Notes**: hornero/flight.py — TraceWriter (sequenced, redact-at-write, kind enum enforced), read_trace/slice_events/parse_range, tolerant Claude Code adopter (unknown shapes degrade to message, corrupt lines skipped, raw payload preserved). MulticodersDispatch.dispatch(brief, run_ref) wraps every dispatch in run.started/run.finished; MockBackend emits a synthetic message/tool_use/tool_result stream (F9 fixture); _UnavailableBackend emits an error event. BuildResult.log_path -> trace_path (schema + build + tests). Ledger agent_runs table + record_agent_run/agent_runs; traceability gains a Runs column. CLI runs list/show/adopt/prune (prune removes trace dirs, audit rows survive). init gitignores .hornero/runs/ + cache/. F9 GATE GREEN. Suite 224 passed.

**Deviations from spec**: zstd compression is feature-detected (zstandard optional dep; plain JSONL stands without it) — hard-requiring it would violate CLAUDE.md invariant 'feature-detect, never hard-require'.

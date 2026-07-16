---
spec: SPEC-004
title: Flight recorder & scribe — capturing, distilling, and auditing agent decisions
status: review
kind: new_feature
created: 2026-07-08
owner: javier@javierleon.dev
depends_on: [SPEC-001, SPEC-003]
amends: [SPEC-001]
---

# SPEC-004 — Flight recorder & scribe: capturing, distilling, and auditing agent decisions

## 1. Context

When a coding agent builds something, its working process — what it explored,
what it tried, what it rejected, why it converged where it did — evaporates
after the result is delivered. Hornero should retain it, for three reasons:
audit ("why does this code look like this?"), memory (the next run should not
re-derive rejected approaches), and trust (HITL reviewers can inspect process,
not just output).

**Epistemological ground rule that shapes this whole spec:** an agent's
narrated reasoning is a *plausible rationalization*, not a guaranteed faithful
readout of its computation. The auditable ground truth is the **action
stream** — tools invoked, files read/edited, commands run, failures and
retries, in order, with timestamps. Narrative summaries are valuable as an
*index over* that stream, never as evidence on their own. Hornero therefore
captures actions as truth (layer 1) and distills narrative as navigation
(layer 2), and every narrative claim must point back into the action stream.

The capture machinery largely exists already:

- Claude Code persists full session transcripts (JSONL) locally and, in
  headless mode, `--output-format stream-json` emits the complete event
  stream; hooks (`PostToolUse`, `SessionEnd`, etc.) allow live capture.
- ai-parrot's dev_loop already streams per-dispatch events
  (`flow:{run_id}:dispatch:*`, FEAT-176 typed lifecycle telemetry).
- Hornero's ledger (SPEC-001 §Persistence) already persists verdicts and
  checkpoints for its own nodes.

This spec formalizes the pipeline: **trace -> decision record -> wiki
synthesis**, one artifact per layer, each with a distinct consumer.

## 2. The three layers

| Layer | Artifact | Consumer | Nature |
|---|---|---|---|
| 1. Flight recorder | `.hornero/runs/<run_id>/trace.jsonl(.zst)` | forensics, scribe, tooling | raw, append-only, complete |
| 2. Decision record | `sdd/decisions/DR-NNN-<slug>.md` | humans + future agents + reconciler retrieval | distilled, evidence-linked |
| 3. Wiki synthesis | `wiki/*` sections linking DRs | anyone entering the repo | narrative map (per SPEC-003 R10: never the primary record) |

## 3. Layer 1 — flight recorder

### 3.1 Capture contract

`DispatchPort` gains an instrumentation requirement: every dispatch MUST
produce a trace. `BuildResult.log_path` (SPEC-001 §7) is re-specified as
`trace_path` pointing at the run's trace file.

- `MulticodersDispatch` + CLI backends: run headless with the provider's
  event-stream output (`claude -p ... --output-format stream-json` for Claude
  Code; equivalent flags per provider; wrapper tee when a provider offers
  none). Interactive SDD sessions (Level 1 supervised work) are covered by
  Claude Code's own transcript files; `hornero run adopt <transcript>` copies
  a session transcript into `.hornero/runs/` and registers it in the ledger.
- Hornero's own nodes (reconciler, wiki updater, report generator) log their
  lifecycle events into the same per-run trace via the ledger checkpoint
  machinery — one run_id namespace for everything.

### 3.2 Trace event envelope

Provider-agnostic normalization (raw provider payload preserved inside):

```json
{"seq": 143, "ts": 1751980000.12, "run_id": "run-ab12cd34",
 "actor": "dispatch:claude-code" ,
 "kind": "tool_use",              
 "summary": "Edit hornero/lifecycle.py (+18 -4)",
 "payload": {"...": "raw provider event"}}
```

`kind` enum: `run.started|run.finished|message|thinking_summary|tool_use|
tool_result|error|retry|hitl.request|hitl.decision`. Sequence numbers make
event ranges citable (§4).

### 3.3 Storage & hygiene

- Location: `.hornero/runs/<run_id>/trace.jsonl`, zstd-compressed on run
  close. Gitignored by default; `config.yaml: runs.commit: true` opts into
  committing compressed traces for fully self-contained audit repos.
- Ledger gains a `runs` table: run_id, spec_id, task_id, actor, status,
  trace_path, started/finished timestamps — the join point between specs,
  tasks, PRs, and traces (extends SPEC-001's traceability report with a
  "process" column).
- **Redaction at write time** (SPEC-003 §9 `redact()` applied to every event
  before it touches disk) — traces are the highest-risk surface since they
  contain raw tool output.
- Retention: `hornero runs prune --keep-days N` (default: keep everything;
  traces are cheap once compressed).

## 4. Layer 2 — the scribe (decision records)

A post-run step that distills the trace into a Decision Record. Runs
automatically at dispatch close (and via `hornero scribe <run_id>` for
adopted or historical traces).

### 4.1 DR template (added to `sdd/templates/decision_record.md`)

```markdown
---
dr: DR-NNN
run_id: run-ab12cd34
spec: SPEC-00X          # and task id when applicable
date: 2026-07-08
actor: dispatch:claude-code
outcome: completed      # completed|failed|needs_human
---

# DR-NNN — <what was built/decided>

## Approach taken
<what was done, in 3-8 sentences>                     [e#12-e#40]

## Alternatives considered and rejected
- <alternative>: rejected because <reason>            [e#55-e#61]

## Deviations from plan / spec
- <deviation + justification, or "none">              [e#88]

## Failures and retries
- <what failed, what the retry changed>               [e#70-e#79]

## Learnings for future runs
- <gotchas, constraints discovered>                   [e#95]
```

### 4.2 Scribe rules

- S1. **Every claim carries an event-range citation** `[e#N-e#M]` into the
  trace. A claim the scribe cannot anchor to events is dropped, not kept —
  the verbatim-evidence invariant (SPEC-001 hard invariant 1) applied to the
  system's own self-description.
- S2. The scribe reads the trace, not the model's memory: it is a separate
  invocation whose only input is the trace file (+ the spec for context).
  This keeps layer 2 honest — it summarizes what *happened*, not what the
  builder *felt* happened.
- S3. `thinking_summary` events may inform tone/ordering but MUST NOT be the
  sole evidence for a claim; at least one action event (`tool_use`,
  `tool_result`, `error`) anchors every substantive statement.
- S4. DRs are subject to the no-op/diff-budget discipline: a trivial run
  (e.g., a no-op wiki update) yields no DR; the scribe states "no decision
  content" in the run log instead of fabricating one.
- S5. DRs land in the same PR as the code they describe (extends SPEC-001
  §11's atomic PR: code + spec + reports + **DR**).

### 4.3 What the reconciler gains

`sdd/decisions/` is indexed by `reindex` (it already is, per SPEC-002 §2) —
so rejected alternatives become retrievable memory. Concretely: when a new
signal proposes an approach a past DR rejected, the reconciler's research
phase surfaces the DR, and the delta preview shows the human "note: DR-014
rejected this approach because X" before they approve a repeat.

## 5. Layer 3 — wiki synthesis

Per SPEC-003 R10, the wiki never stores primary records. The wiki updater:

- links relevant DRs from the affected area pages ("decision history" of a
  module = the DRs that shaped it);
- may promote a *durable* learning from a DR into a page's "what to watch
  out for" section (W5), citing the DR;
- `wiki/quickstart.md` links `sdd/decisions/` as the decision-history
  entrypoint.

Result: someone auditing "why does this code look like this?" navigates
wiki page -> DR -> event range -> raw trace, each hop adding resolution.

## 6. CLI surface

```
hornero runs list [--spec SPEC-00X]
hornero runs show <run_id> [--kind tool_use,error] [--range e#12:e#40]
hornero runs adopt <claude-code-transcript.jsonl>
hornero scribe <run_id> [--force]
hornero runs prune --keep-days N
```

`runs show --range` is what makes DR citations one command away from raw
evidence.

## 7. Phases

| Phase | Deliverable | Gate (deterministic) |
|---|---|---|
| **F9 — recorder** | event envelope + normalizer, trace capture in `MulticodersDispatch` (mock backend emits synthetic events), ledger `runs` table, redaction-at-write, `runs list/show/adopt` | fixture dispatch (mock) produces a complete ordered trace; planted secrets absent from trace bytes; `runs show --range` returns exact event slices; adopt registers a fixture Claude Code transcript |
| **F10 — scribe** | DR template, scribe distiller (FakeLLM-tested), citation verifier, PR integration | fixture trace -> DR where every claim's `[e#N-e#M]` resolves to real events (mechanically verified); unanchorable-claim fixture -> claim dropped + logged; trivial-run fixture -> no DR |
| **F11 — synthesis + retrieval** | wiki DR-linking, reindex of decisions, reconciler "past rejection" surfacing | fixture: signal re-proposing a DR-rejected approach -> delta preview includes the DR reference |

Ordering: F9 has zero LLM dependency (mock events) and can interleave right
after F3 (dispatch bridge) since it instruments the same seam.

## 8. Risks

- **R13. Narrative laundering** — the DR reads authoritative but misstates
  what happened. Mitigation: S1-S3 (action-anchored citations, trace-only
  input, mechanical citation verification); the trace remains the record of
  truth and is one `runs show` away.
- **R14. Trace volume.** Mitigation: zstd (JSONL event streams compress
  ~10-20x), gitignored by default, prune command; payload truncation caps
  per-event size with full output retrievable from tool logs when needed.
- **R15. Sensitive content in traces** (they see everything the agent saw).
  Mitigation: redaction at write time, not at read time; commit opt-in only;
  R9/§9 secret-scan gate reused before any trace leaves the machine.
- **R16. Scribe cost creep** (an LLM call per run). Mitigation: S4 no-op
  rule; scribe uses the cheap summary-model tier (same pattern as
  `DEV_LOOP_SUMMARY_LLM`); batchable via `hornero scribe` for backlogs.

## 9. Open questions

- OQ11. Should `hitl.decision` events (approve/reject/edit, with who and
  when) also flow into a human-readable approvals log in `sdd/decisions/`?
  Leaning yes — it completes the audit chain with the *human's* decisions,
  not just the agent's. Decide in F10.
- OQ12. Cross-run DR threading: when a revision run supersedes a prior run's
  approach, should the new DR mark the old one `superseded_by`? Cheap and
  useful; decide in F10.
- OQ13. Adopt-path fidelity: Claude Code's local transcript format is
  undocumented/unstable across versions. Pin a tolerant parser with
  golden-file tests per observed version, or restrict `adopt` to
  stream-json captures only? Decide in F9 with real samples.

## Log

- 2026-07-08 — Spec drafted. Motivated by the requirement to retain and
  audit agent decision processes; grounded in the action-stream-as-truth /
  narrative-as-index distinction. Capture reuses Claude Code transcripts /
  stream-json / hooks and the dev_loop FEAT-176 telemetry pattern.
- 2026-07-08 — Approved by owner (autonomous-mode directive); decomposition
  + implementation begins. SPEC-001/002 complete, so phases F6+ are unblocked.
- 2026-07-08 — All 3 tasks (033-035) completed; gates F9, F10, F11 verified
  green verbatim (ordered mock trace + zero secret bytes + exact range
  slices + transcript adoption; mechanically verified DR citations with
  unanchored claims dropped; DR-rejected approach surfaced in the HITL
  preview). OQ11/OQ12 deferred (approvals log, DR threading); OQ13 resolved
  tolerantly (unknown transcript shapes degrade to message events).
- 2026-07-14 — build started (run r-1, backend mock).
- 2026-07-14 — PR opened: https://example.invalid/pr/SPEC-004-4

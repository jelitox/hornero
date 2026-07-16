# Autonomous improvement program - progress checkpoint

Last updated: 2026-07-16
Authority: SPEC-005
Status: complete

## Resume protocol

1. Read `sdd/specs/SPEC-005-autonomous-project-intelligence.md`.
2. Read this file from top to bottom.
3. Read `sdd/tasks/index/autonomous-project-intelligence.json`.
4. Run `git status --short` and preserve changes not attributed here.
5. Run the gate recorded under `Last verified gate`.
6. Continue the first task marked `in_progress`, otherwise the first pending
   task whose dependencies are done.
7. Update this checkpoint before switching tasks or ending a session.

## Current phase

F12 through F16 are implemented and release-gated. Documentation and all
TASK-036 through TASK-055 completion records are current. The repository graph
was rebuilt and validated after implementation.

## Task board

| Task | Audit item | State | Depends on |
|---|---:|---|---|
| TASK-036 | 1 path containment | done | none |
| TASK-037 | 2 knowledge redaction | done | 036 |
| TASK-038 | 3 prompt trust boundary | done | 037 |
| TASK-039 | 4 atomic build | done | none |
| TASK-040 | 5 concurrent run IDs | done | none |
| TASK-041 | 6 truthful apply outcomes | done | 040 |
| TASK-042 | 7 strict config schema | done | none |
| TASK-043 | 8 durable delta queue | done | 040 |
| TASK-044 | 9 repository root discovery | done | none |
| TASK-045 | 10 index recovery | done | 037, 044 |
| TASK-046 | 11 project factory | done | 036, 042, 044 |
| TASK-047 | 12 blueprint engine | done | 046 |
| TASK-048 | 13 semantic graph | done | 037, 045 |
| TASK-049 | 14 provenance | done | 048 |
| TASK-050 | 15 graph validator | done | 049 |
| TASK-051 | 16 document ingestion | done | 036, 037 |
| TASK-052 | 17 real LLM providers | done | 037, 038, 042 |
| TASK-053 | 18 real CLI dispatch | done | 036, 039, 042 |
| TASK-054 | 19 improvement analyzers | done | 049, 050, 051 |
| TASK-055 | 20 autonomous controller | done | 041, 043, 050, 052, 053, 054 |

## Decisions

- Keep all autonomous mutation disabled by default.
- Treat the semantic graph as derived state; Markdown specs, decisions, task
  artifacts, findings, blueprint locks, and run records remain primary records.
- Use stdlib implementations with optional feature detection to preserve the
  single required runtime dependency.
- Implement local command providers before network providers; never pass
  credentials through prompts, traces, or command-line arguments.
- A finding is not a requirement delta. It becomes a proposal/spec only through
  an explicit policy decision, retaining the finding as provenance.
- A successful autonomous execution is `ready_for_review`, not `applied`:
  Hornero retains a branch but never claims it was merged.
- `reconcile` and non-empty `build` validate without mutation and block stale
  or corrupt graph state; improvement stages may explicitly repair derived state.

## Work completed

- Audited current architecture and existing CODE_REVIEW/PAGEINDEX records.
- Verified baseline: 237 tests passed; ruff and mypy clean.
- Created SPEC-005, task index, task artifacts, and this checkpoint.
- Completed F12: centralized path containment across toolkit operations;
  redacted derived knowledge; isolated untrusted prompt blocks; made build
  preflight/termination truthful; added atomic run allocation and distinct
  decision/outcome fields; enforced config types; preserved queue state across
  no-TTY runs; added verified root discovery; quarantined/rebuilt corrupt
  derived indexes.
- Completed F13: `hornero new`, three composable built-in blueprints, safe
  templating, Git/bootstrap, lock hashes and non-mutating drift status.
- Completed F14: SQLite semantic entities/relations/provenance for requirements,
  criteria, controls, tasks, code, tests, decisions, findings and ledger runs;
  offline navigation, stable validation findings and repair preflights.
- Completed F15: bounded/redacted document ingestion, local-command and
  OpenAI-compatible model providers, and real argv/JSON coding CLI dispatch.
- Completed F16: nine deterministic policy packs and default-off bounded
  scan/plan/run/status controller with exact risk approval, isolated worktrees,
  gates, rollback, review branches, ledger outcomes and graph learning.
- Updated README, usage/development guides, changelog and package version 0.3.0.

## Last verified gate

Final release gate after TASK-036 through TASK-055:

```text
pytest -q: 291 passed in 11.50s
ruff check .: passed
mypy hornero: passed (56 source files)
hornero validate --repair: fresh, 0 blocking, 4 warnings
knowledge graph: 259 pages, 488 edges, 982 semantic entities,
                 882 semantic relations, 1864 provenance records
```

## Next action

No remaining action for the approved 20-item program. On the next improvement
cycle, run `hornero improve scan` and `hornero improve plan --limit 20`; request
owner feedback when a new batch reaches 20 items or policy requires HITL.

## Known pre-existing worktree changes

At program start the worktree already contained modifications to README, CLI,
knowledge/reindex, docs, all four prior specs, report tests, and untracked code
graph/reports/reviews/runtime files. These are treated as owner work and are not
to be reverted.

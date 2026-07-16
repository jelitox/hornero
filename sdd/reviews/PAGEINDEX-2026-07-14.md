# PageIndex: hornero codebase

Date: 2026-07-14
Scope: 46 Python source files, 34 pytest files, SDD specs/tasks, docs, examples.
Purpose: compact knowledge-base index for agents and maintainers. This file is
under `sdd/`, so `hornero reindex` includes it in `.hornero/knowledge/`.

## Query starters

- CLI command routing: `hornero cli init reconcile build report sdd wiki runs scribe`
- Reconcile pipeline: `signals evidence HITL apply deltas ledger`
- Build dispatch: `approved specs BuildBrief mock cli api trace scribe`
- SDD toolkit sync: `manifest lock drift install sync push workspace`
- Knowledge layer: `pageindex graphindex fallback token overlap reindex`
- Review findings: `path traversal scaffold_dirs build partial mutation queued deltas`

## System map

Hornero is a repo-native product loop: signals enter through adapters, the
reconciler drafts and verifies requirement deltas, humans approve changes, specs
act as the tracker, approved specs dispatch builds, and reports/wiki/knowledge
indexes keep auditability inside the repo.

Primary invariants:

- Evidence excerpts must be verbatim substrings of their source signal.
- No TTY or approval channel means no spec mutation.
- API dispatch is never an implicit fallback.
- Diverged SDD toolkit files are never auto-merged.
- Offline deterministic tests are the expected gate.

## Entrypoints

| Path | Role | Important neighbors |
|---|---|---|
| `hornero/cli.py` | Argparse command surface. Delegates `init`, `status`, `reconcile`, `build`, `reindex`, `report`, `runs`, `scribe`, `wiki`, `sdd`. | `build.py`, `reconciler/run.py`, `reports/run.py`, `sdd_toolkit/cli_sync.py` |
| `hornero/build.py` | Approved specs to dispatch briefs and trace-backed build results. Transitions specs through `building`, `review`, `needs_human`. | `adapters/dispatch.py`, `memory/ledger.py`, `scribe.py` |
| `hornero/reconciler/run.py` | Main signal-to-spec pipeline: poll sources, draft deltas, budget/queue, HITL gate, apply, ledger. | `draft.py`, `hitl.py`, `apply.py`, `memory/knowledge.py` |
| `hornero/reports/run.py` | Registry and CLI gate for deterministic HTML reports. | `reports/engine.py`, `reports/capabilities.py`, `reports/workflows.py`, `reports/traceability.py` |

## Core domain modules

| Path | Responsibility | Test coverage |
|---|---|---|
| `hornero/models.py` | `RequirementDelta`, `Evidence`, `DeltaKind`, evidence verification. | `tests/test_models.py`, `tests/test_draft.py` |
| `hornero/ports.py` | Typed contracts for signals, tracker, dispatch, build brief/result. | `tests/test_ports.py` |
| `hornero/lifecycle.py` | Spec frontmatter parsing, status machine, status transitions, corpus lookup. | `tests/test_lifecycle.py` |
| `hornero/criteria.py` | Acceptance criterion parser; allowlisted shell commands vs manual criteria. | `tests/test_criteria.py` |
| `hornero/config.py` | `.hornero/config.yaml`, default config, unknown-key fail-closed behavior. | `tests/test_cli.py`, e2e tests |
| `hornero/layout.py` | Single resolver for native `sdd/` directory layout. | Used across tests |
| `hornero/redact.py` | Shared secret scanning and redaction for generated surfaces. | `tests/test_redact.py`, `tests/test_gitsource.py` |
| `hornero/watermarks.py` | Watermark read/write and content snapshots for no-op discipline. | `tests/test_watermarks.py` |
| `hornero/hooks.py` | Optional post-merge hook and CI snippet for reindex. | CLI tests |
| `hornero/instructions.py` | Injects hornero guidance into agent instruction files. | `tests/test_instructions.py` |
| `hornero/llm.py` | Model resolver, currently fake-script backed for deterministic MVP. | `tests/test_models.py`, reconciler/wiki/scribe tests |

## Adapters

| Path | Responsibility | Notes |
|---|---|---|
| `hornero/adapters/inbox.py` | Filesystem `SignalSource`: `.hornero/inbox/` to `.hornero/processed/`. | Signal ids use mtime date plus content hash. |
| `hornero/adapters/gitsource.py` | Optional git commit digest source, redacted and watermark-scoped. | Emits digest files under `.hornero/gitsource/`; ack moves digest to processed. |
| `hornero/adapters/repo_tracker.py` | Tracker implementation that writes status transitions and comments into spec markdown. | Owns spec-as-tracker mutations outside apply/build flows. |
| `hornero/adapters/dispatch.py` | Build brief rendering and backend resolution. Provides deterministic mock backend and unavailable-backend stand-ins. | API backend only honored as explicit first entry. |

## Reconciler package

| Path | Responsibility | Notes |
|---|---|---|
| `hornero/reconciler/draft.py` | Builds LLM prompt, parses strict JSON, constructs deltas, drops bad evidence or malformed items. | Ledger records dropped drafts. |
| `hornero/reconciler/hitl.py` | Terminal approval channel, render preview, edit-in-editor, `gate()`. | Duplicate deltas are always skipped. |
| `hornero/reconciler/apply.py` | Only writer of `sdd/specs/` in reconcile. Applies NEW, CHANGED, OBSOLETE and writes proposals/ADRs. | Exact-context unified diff application. |
| `hornero/reconciler/run.py` | Orchestrates source polling, queued deltas, HITL, apply, duplicate comments, ledger statuses. | Budget is `DELTA_BUDGET = 5`. |
| `hornero/reconciler/testing.py` | `FakeLLM` and deterministic prompt matching for tests. | Used broadly by e2e tests. |

## Memory and knowledge

| Path | Responsibility | Artifacts |
|---|---|---|
| `hornero/memory/knowledge.py` | Feature-detects `parrot.knowledge.pageindex`/`graphindex`; falls back to token overlap. | Retrieval roots are `sdd/` and `.hornero/processed/`. |
| `hornero/memory/reindex.py` | Deterministic writer of `.hornero/knowledge/manifest.json` and fallback index. | Scans `.md`, `.txt`, `.vtt`. |
| `hornero/memory/ledger.py` | SQLite audit ledger for runs, deltas, drops, dispatches, agent runs, checkpoints. | Operational state, gitignored by default. |

## Dispatch, flight recorder, and scribe

| Path | Responsibility | Notes |
|---|---|---|
| `hornero/flight.py` | Redacted action-stream trace writer/reader, optional zstd compression, transcript adoption. | Events are the ground truth for DRs. |
| `hornero/scribe.py` | Converts a trace into a verified Decision Record with event-range citations. | Drops unanchored claims. |
| `hornero/build.py` | Dispatch lifecycle and post-build report regeneration. | Registers dispatches and agent runs in ledger. |

## Reports package

| Path | Responsibility |
|---|---|
| `hornero/reports/engine.py` | Shared report context, HTML skeleton, deterministic rendering helpers. |
| `hornero/reports/capabilities.py` | Capabilities report generation. |
| `hornero/reports/workflows.py` | Workflow report generation. |
| `hornero/reports/traceability.py` | Signal/delta/spec/dispatch traceability report. |
| `hornero/reports/run.py` | Report registry and CLI command implementation. |

## Wiki

| Path | Responsibility |
|---|---|
| `hornero/wiki.py` | Agent-facing wiki generator/updater with LLM JSON contracts, link checks, stub checks, diff budget, and no-op watermark discipline. |

## SDD toolkit sync

| Path | Responsibility | Notes |
|---|---|---|
| `hornero/sdd_toolkit/manifest.py` | Reads upstream `sdd-toolkit.manifest.json`, fallback manifest, managed glob expansion. | Review finding: manifest paths need containment validation. |
| `hornero/sdd_toolkit/upstream.py` | Fetches local or git upstream into cache, degrades to stale cache when possible. | Network is isolated behind subprocess git. |
| `hornero/sdd_toolkit/lock.py` | `.hornero/sdd.lock` dataclasses, hash helpers, policy mutation. | Policies: `sync`, `local`, `pinned`. |
| `hornero/sdd_toolkit/install.py` | Installs/adopts toolkit files, scaffolds state dirs, preserves local edits unless forced. | Review finding: scaffold paths can escape repo if manifest is malicious. |
| `hornero/sdd_toolkit/drift.py` | Three-way drift classifier and pull application. | Diverged files are reported, never auto-merged. |
| `hornero/sdd_toolkit/cli_sync.py` | CLI layer for status/diff/sync/hold/unhold/pin and explicit resolutions. | Writes lock identity after sync. |
| `hornero/sdd_toolkit/push.py` | Per-file upstream promotion flow, secret scan, runner seam, workspace fanout. | Uses injected runner for `git`/`gh`. |

## Tests index

| Area | Tests |
|---|---|
| CLI/init/status | `tests/test_cli.py`, `tests/test_instructions.py`, `tests/test_hooks.py` if added later |
| Models/lifecycle/criteria | `tests/test_models.py`, `tests/test_lifecycle.py`, `tests/test_criteria.py`, `tests/test_ports.py` |
| Reconcile/evidence/HITL/apply | `tests/test_reconcile_e2e.py`, `tests/test_draft.py`, `tests/test_hitl.py`, `tests/test_apply.py` |
| Knowledge/reindex | `tests/test_knowledge.py`, `tests/test_reindex.py` |
| Build/dispatch/flight/scribe | `tests/test_build_e2e.py`, `tests/test_dispatch.py`, `tests/test_flight.py`, `tests/test_scribe.py`, `tests/test_dr_retrieval.py` |
| Reports | `tests/test_reports_e2e.py`, `tests/test_reports_capabilities.py`, `tests/test_writeback_e2e.py` |
| SDD toolkit | `tests/test_sdd_manifest.py`, `tests/test_sdd_install.py`, `tests/test_sdd_lock.py`, `tests/test_sdd_drift.py`, `tests/test_sdd_sync_cli.py`, `tests/test_sdd_push.py`, `tests/test_sdd_upstream.py`, `tests/test_sdd_drift.py` |
| Signals/adapters | `tests/test_inbox.py`, `tests/test_gitsource.py`, `tests/test_repo_tracker.py` |
| Wiki/redaction/watermarks | `tests/test_wiki.py`, `tests/test_redact.py`, `tests/test_watermarks.py` |

## Documentation and SDD corpus

| Path | Purpose |
|---|---|
| `README.md` | Product overview, quickstart, CLI summary, hard invariants. |
| `docs/USAGE.md` | Full usage loop and configuration details. |
| `docs/DEVELOPMENT.md` | Architecture map, quality gates, SDD workflow. |
| `docs/DEPLOYMENT.md` | Adoption/deployment guidance. |
| `docs/artefacts/` | Generated visual HTML artifacts in English and Spanish. |
| `sdd/specs/` | Source-of-truth product specs. |
| `sdd/tasks/completed/` | Completed SDD task records. |
| `sdd/tasks/index/` | JSON indexes for SDD tasks. |
| `sdd/templates/` | Templates/prompts for SDD artifacts. |
| `sdd/reviews/` | Review and pageindex artifacts, including this file. |

## Current review companion

See `sdd/reviews/CODE_REVIEW-2026-07-14.md` for findings, residual risks,
and verification commands from the 2026-07-14 review.

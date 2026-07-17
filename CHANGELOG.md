# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[SemVer](https://semver.org/).

## [Unreleased]

### Added

- Automatic wheel and source-distribution publication after every successful
  push to master, using immutable PEP 440 post-release versions, PyPI Trusted
  Publishing, PEP 740 attestations, installed-wheel smoke tests, least-
  privilege jobs and commit-pinned GitHub Actions.

## [0.4.0] — 2026-07-16

SPEC-006 adds production-grade graph intelligence, factory evolution,
assurance evidence and a bounded event runtime across 20 completed features.

### Added

- Temporal graph snapshots and entity versions, explicit supersession,
  contradiction/duplicate candidates, impact traversal, traceability coverage,
  semantic queries/explanations and hard-budget context packs.
- AI-assisted knowledge extraction whose proposed entities survive only when
  their evidence excerpt is a verbatim substring of the source document.
- HMAC-signed local/HTTPS blueprint registry envelopes, schema 2 locks with
  generated bases, three-way upgrades and explicit divergence resolution.
- Capability-aware production stacks for database/migrations, authentication,
  queueing, telemetry, containers, IaC, CI and shared API/event/data contracts.
- Federated workspace graphs and bounded cross-repository impact plans.
- Expiring finding baselines with owner/reason, declarative local policy rules,
  offline CycloneDX SBOM/vulnerability feeds, STRIDE threat models, and
  evidence mappings for SOC 2, ISO 27001, GDPR and PCI.
- Persistent schedules and HMAC webhooks with replay protection, resource
  sandboxing, cost/event budgets, retries, risk approvals, explicit push/PR
  policy, runtime metrics and bounded feedback-derived rule weights.

### Safety

- Scheduled code mutation requires an explicitly configured sandbox wrapper.
  Subprocess environments exclude credentials by default and apply CPU,
  memory, file-size and process limits.
- PR creation requires runtime push enablement, event-level `allow_push`, and a
  named approval. No runtime path merges the default branch.

## [0.3.0] — 2026-07-16

SPEC-005 implements the autonomous project-intelligence program and closes the
20-item security, reliability, factory, graph, provider and improvement audit.

### Added

- `hornero new` and versioned composable blueprints with safe rendering,
  lockfile hashes and non-mutating drift status.
- A typed semantic graph connecting sources, requirements, criteria, controls,
  tasks, decisions, code, tests and findings, with source-hash provenance;
  `hornero validate` repairs derived state and reports stable validation IDs.
- Bounded document ingestion for text/Markdown/VTT/HTML/JSON/YAML/DOCX and
  optional PDF, including normalized Markdown and provenance sidecars.
- Explicit local-command and OpenAI-compatible LLM providers with environment
  credentials, budgets, timeouts, retries and redacted/hash-only auditing;
  real coding CLI dispatch uses JSON over stdin/stdout and argv without shell.
- `hornero improve scan|plan|run|status`: nine deterministic policy packs,
  stable finding lifecycle, risk/HITL policy, isolated worktree execution,
  gates, review branches, rollback and ledgered learning.

### Security and reliability

- Central path containment rejects traversal and symlink escape across toolkit
  and generated-project writes; strict configuration rejects wrong shapes.
- Knowledge is redacted before persistence and untrusted prompt blocks are
  JSON-delimited; corrupt derived indexes are quarantined and rebuilt.
- Run IDs are atomic, delta decision/outcome state is truthful, queues survive
  non-interactive runs, project roots are marker-verified, and build preflight
  cannot leave partial lifecycle transitions.

## [0.2.0] — 2026-07-08

SPEC-003 (agent-facing wiki, git watermarks, code-as-signal) and SPEC-004
(flight recorder & scribe) fully built — gates F6 through F11 green. 234
deterministic tests.

### Added — wiki, watermarks, code-as-signal (SPEC-003)

- **Git watermarks + no-op discipline**: committed `.hornero/watermarks.json`
  (one entry per surface); `report`/`reindex`/`wiki update` snapshot their
  output tree and say "already current" instead of churning — a quiet repo
  costs one hash comparison, so scheduled CI runs produce no PR on quiet days.
- **`hornero wiki init|update`**: LLM-drafted, mechanically gated agent-facing
  wiki (`wiki/`): mandatory quickstart, anti-stub + small-repo caps, relative
  link checker, surgical updates scoped to the git change window (empty
  window = zero model calls), diff budget (U2), formatting-only edits
  reverted (U3), redacted writes.
- **Instruction injection**: `init` and `sdd install` keep a standardized
  `## Hornero` section in top-level `CLAUDE.md`/`AGENTS.md` — semantic
  staleness only, idempotent, neighbors preserved.
- **`GitSource`** (opt-in `signal_sources: [inbox, git]`): commits since the
  watermark become one redacted digest signal (messages + stats, never
  diffs); hornero-authored commits excluded; spec drift detected from the
  code side.
- **Delta budget**: max 5 fresh deltas per signal per run; the excess is
  queued in the ledger and re-presented next run — never dropped.
- **Shared `redact()` layer**: secret shapes + live env values scrubbed from
  every generated surface (reports, wiki, digests, traces).
- **CI examples**: GitHub Actions + GitLab scheduled-update pipelines
  (PR-gated, never direct push; reconcile only as dry-run advisory).

### Added — flight recorder & scribe (SPEC-004)

- **Flight recorder**: every dispatch produces an append-only, redacted,
  sequenced JSONL trace under `.hornero/runs/<run_ref>/` (zstd when
  available); ledger `agent_runs` table joins specs ↔ tasks ↔ traces;
  traceability report gains a Runs column.
- **`hornero runs list|show|adopt|prune`**: inspect traces (`--kind`,
  `--range e#N:e#M`), adopt Claude Code session transcripts (tolerant
  parser), prune old trace dirs (audit rows survive).
- **The scribe** (`hornero scribe <run>`, auto at dispatch close when
  `models.scribe` is set): distills a trace into a Decision Record in
  `sdd/decisions/DR-NNN-*.md` where **every claim carries an event-range
  citation that is mechanically verified** — unanchorable claims are dropped
  and logged, trivial runs yield no DR.
- **Institutional memory**: DRs are indexed as decisions; when a new signal
  re-proposes an approach a past DR rejected, the HITL preview shows
  `[memory] DR-NNN ...` before the human decides. Wiki quickstart links the
  decision history.

## [0.1.0] — 2026-07-08

First complete release: SPEC-001 (product loop MVP, gates F1–F5) and SPEC-002
(SDD toolkit sync, gates F2.5/F3.5/F4.5) fully built. 189 deterministic
tests; ruff + mypy clean.

### Added — product loop (SPEC-001)

- **Core model**: ports (`Signal`, `SignalSource`, `TrackerPort`,
  `DispatchPort`), `RequirementDelta` with mechanically verified verbatim
  evidence (mismatched drafts are dropped and ledger-logged, never repaired).
- **Spec lifecycle**: markdown specs with YAML frontmatter as the tracker
  (`proposed → approved → building → review → done`, plus
  `rejected/needs_human/obsolete`); status transitions and comments are
  written into the spec files themselves.
- **`hornero init/status`**: idempotent scaffold of `.hornero/` + the `sdd/`
  layout; config with fail-closed unknown-key handling; SQLite audit ledger.
- **Inbox signal source**: `.hornero/inbox/` → poll → ack →
  `.hornero/processed/`.
- **Reconciler (F2)**: signals → drafted deltas (`NEW/CHANGED/OBSOLETE/
  DUPLICATE`) → interactive HITL gate (approve/reject/edit/skip; fail-closed
  without a TTY) → apply. Exact unified-diff patching; `OBSOLETE` writes ADRs;
  `--dry-run` guarantees a clean `git status`.
- **Dispatch (F3)**: approved spec → `BuildBrief` (body + linked ADRs +
  write-back contract) → backend order `mock`/`cli`/`api`, with `api` strictly
  opt-in-first-entry and never a fallback; operational failures return
  `failed`/`needs_human`, never raise.
- **Memory (F4)**: deterministic knowledge index over the `sdd/` corpus +
  processed signals; `parrot.knowledge.pageindex`/`graphindex`
  feature-detected with a first-class token-overlap fallback; post-merge
  reindex hook and CI snippet; write-back loop closure with DUPLICATE
  signal-strength telemetry.
- **Reports (F5)**: offline, deterministic `capabilities.html`,
  `workflows.html` and `traceability.html` (audit chain signal → delta → spec
  → SDD tasks → PR → merge, with explicit gaps).

### Added — SDD toolkit sync (SPEC-002)

- **Native SDD layout**: `sdd/{specs,decisions,reports,proposals,tasks,...}`
  replaces `product/`; low-confidence NEW deltas become brainstorm proposals
  in `sdd/proposals/` instead of errors; the knowledge layer indexes the full
  `sdd/` corpus; traceability gains an "SDD tasks" column read from
  `sdd/tasks/index/*.json`.
- **`hornero sdd install`**: manifest-driven managed set (with built-in
  fallback patterns), shallow blobless upstream cache that tolerates being
  offline, state-dir scaffold, and a committed `.hornero/sdd.lock` (upstream +
  installed hashes + per-file policy). Adoption over clobbering: identical
  pre-existing files lock as `current`, hand-modified ones as `modified`;
  re-runs are byte-idempotent.
- **Three-way drift engine**: per-file states `current/behind/modified/
  diverged/deleted_locally/new_upstream` (+ `held`/`pinned` by policy)
  computed from upstream-now vs both lock legs vs disk. **Diverged files are
  never auto-resolved** — no timestamp heuristics.
- **`hornero sdd status/diff/sync/hold/unhold/pin`**: drift table; unified
  diffs; pull sync that fast-forwards what is safe, reinstalls deletions only
  with `--force`, blocks with exit ≠ 0 on unresolved divergence, and accepts
  explicit `--theirs` (upstream wins) / `--ours` (local wins, lock
  re-baselined) resolutions; `--dry-run` writes nothing.
- **`hornero sdd sync --push`**: per-file, explicit, PR-gated promotion to the
  upstream (`sdd-toolkit/promote-<repo>` branch via injected runner; never the
  default branch) with a secret scan (AWS keys, GitHub tokens, `sk-` keys,
  bearer tokens, private-key blocks, credentialed URLs) and a per-run
  `--allow-secrets` override.
- **`hornero sdd sync --workspace <dir>`**: pull-sync fanout over immediate
  child repos carrying a lockfile; each syncs against its own lock identity;
  worst child exit code propagates.

### Fixed

- Drift classification uses both lock legs, so files that `install` adopted
  as locally modified read `modified` (push candidates) instead of `behind` —
  a pull can no longer clobber a file adoption deliberately kept; an upstream
  move over such a file reads `diverged` for a human decision.

[0.1.0]: https://keepachangelog.com/en/1.1.0/

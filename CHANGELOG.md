# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[SemVer](https://semver.org/).

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

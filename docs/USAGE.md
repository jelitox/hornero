# Usage guide

How to run the hornero product loop in a repository, end to end.

## 1. Initialize

```bash
cd your-project/
hornero init
```

This scaffolds:

```
.hornero/                 runtime state (ledger is gitignored automatically)
  inbox/                  drop requirement signals here
  processed/              acked signals move here (still indexed as knowledge)
  knowledge/              deterministic retrieval index (built by `reindex`)
  config.yaml             created once, never overwritten
  ledger.db               SQLite audit ledger (runs, deltas, dispatches)
sdd/                      the spec corpus — hornero's native layout
  specs/                  SPEC-NNN-<slug>.md (frontmatter is the tracker)
  decisions/              ADR-NNN-<slug>.md
  proposals/              low-confidence ideas as brainstorm docs
  reports/                generated HTML
  tasks/ state/ reviews/  SDD workflow state
```

Options:

- `--hooks` — also install a post-merge git hook that runs `hornero reindex`.
- `--print-ci-hook` — print a CI snippet for the same thing, write nothing.
- `--no-sdd` — skip the SDD-toolkit install step.

If `.hornero/config.yaml` sets `sdd_upstream`, `init` finishes by running
`hornero sdd install` against it. Without an upstream it just prints a hint —
init is offline-safe by default.

## 2. Configuration (`.hornero/config.yaml`)

```yaml
signal_source: inbox          # SignalSource adapter
tracker: repo                 # TrackerPort adapter (spec files ARE the tracker)
dispatch:
  backend_order: [mock]       # 'api' is NEVER added automatically
criterion_allowlist: [pytest, ruff, mypy, python]   # runnable acceptance criteria
models: {}                    # reserved for LLM model routing
sdd_upstream: ""              # toolkit source: git URL or local path
sdd_ref: main
```

Unknown keys fail closed with an error — typos never get silently ignored.

## 3. Feed signals

A signal is any markdown/text file dropped into `.hornero/inbox/`: meeting
notes, a Slack export, a customer email, a half-formed idea.

```bash
cp meeting-notes-2026-07-08.md .hornero/inbox/
```

## 4. Reconcile (signals → specs, with a human gate)

```bash
hornero reconcile --dry-run   # preview the deltas; guaranteed zero writes
hornero reconcile             # interactive review, then apply
```

What happens:

1. Every pending signal is polled and compared against the spec corpus and
   the knowledge index.
2. Draft **RequirementDeltas** are produced — kind `NEW`, `CHANGED`,
   `OBSOLETE` or `DUPLICATE` — each carrying evidence excerpts that are
   **mechanically verified substrings** of the signal. A draft whose evidence
   does not match verbatim is dropped and logged (`evidence_mismatch`), never
   "fixed".
3. Each surviving delta is presented in your terminal:

   ```
   [NEW] dlt-r-3-1 — Weekly digest email
     summary:    ...
     confidence: 0.85  (informational only)
     evidence:
       sig-20260708-a1b2c3 @ L14: 'users keep asking for a weekly digest'
     proposed patch: ...
   [a]pprove / [r]eject / [e]dit / [s]kip >
   ```

   `e` opens `$EDITOR` on the patch; an empty or unavailable editor rejects
   (never auto-approves). **No TTY ⇒ nothing is applied** — the gate is
   fail-closed.
4. Approved deltas are applied:
   - `NEW` with a valid spec patch → `sdd/specs/SPEC-NNN-<slug>.md`, born
     `proposed`, transitioned to `approved`, with the signal ids in
     `sources:`.
   - `NEW` with a prose (non-spec) patch → a brainstorm proposal in
     `sdd/proposals/<slug>.brainstorm.md` — an idea worth keeping is not an
     error.
   - `CHANGED` → exact unified diff applied to the affected spec; a stale
     diff fails cleanly and leaves the file untouched.
   - `OBSOLETE` → status transition + an ADR in `sdd/decisions/` when an
     existing ADR mentions the spec.
5. A signal is acked (moved to `processed/`) only after at least one human
   decision on it and zero failed applications. Skipped-only signals stay in
   the inbox.

## 5. Build (approved specs → coding agents)

```bash
hornero build                 # all approved specs
hornero build SPEC-002        # just one
hornero build --backend mock  # force a backend for this run
```

Each approved spec is rendered into a **BuildBrief** (spec body + linked ADRs
+ the write-back contract) and dispatched through the backend order:

- `mock` — deterministic built-in backend (default; great for testing the loop).
- `cli` — your local coding-agent CLI, using **your own session/auth**.
- `api` — billed; runs **only** if you explicitly wrote it first in
  `dispatch.backend_order`. It is never a fallback.

Status transitions are written into the spec file itself
(`approved → building → review`), and every dispatch lands in the ledger with
its log and PR URL. The write-back contract requires code, the transitioned
spec, and regenerated reports to ship in the same branch/PR.

## 6. Memory

```bash
hornero reindex               # rebuild .hornero/knowledge/ deterministically
hornero status                # includes index staleness
```

The knowledge layer indexes the full `sdd/` corpus plus processed signals.
If `parrot.knowledge.pageindex` / `graphindex` are installed they are used;
otherwise a deterministic token-overlap fallback kicks in — same interface,
fully tested.

## 7. Reports

```bash
hornero report                # capabilities + workflows + traceability
hornero report --only traceability
```

All reports are offline, deterministic (byte-identical across runs on the
same state), and interlinked:

- **capabilities.html** — what the product does today, grouped, per done spec.
- **workflows.html** — shipped flows with their ADRs and code references.
- **traceability.html** — the audit chain per requirement: signals → deltas →
  spec (+status) → **SDD tasks** → PR → merged. Gaps render as explicit `—`.

## 8. SDD toolkit sync

Manage shared agent/command/rule files across repos like dependencies:

```bash
hornero sdd install --from ~/repos/sdd-toolkit    # or a git URL
hornero sdd status
hornero sdd diff .claude/commands/sdd-start.md
hornero sdd sync --dry-run
hornero sdd sync
```

- The upstream's `sdd-toolkit.manifest.json` defines the managed set;
  `.hornero/sdd.lock` (committed) records upstream + installed hashes and a
  per-file policy.
- Install **adopts** pre-existing files: identical → `current`; hand-modified
  → kept and locked as `modified` (never clobbered without `--force`).
- Drift states per file: `current`, `behind`, `modified`, `diverged`,
  `deleted_locally`, `new_upstream`, plus `held` / `pinned` by policy.
- `sync` fast-forwards `behind` + `new_upstream`, reinstalls deleted files
  only with `--force`, and **blocks (exit ≠ 0) on `diverged`** until you
  resolve explicitly:

  ```bash
  hornero sdd sync --theirs .claude/commands/sdd-task.md   # upstream wins
  hornero sdd sync --ours   .claude/rules/python.md        # local wins, re-baselined
  ```

- Policies: `hold` (local, never pulled), `pin` (frozen), `unhold` (back to sync).
- Promote your improvements upstream (PR-gated, never to the default branch):

  ```bash
  hornero sdd sync --push .claude/commands/sdd-start.md
  ```

  A secret scan (AWS keys, GitHub tokens, `sk-` keys, bearer tokens, private
  keys, URLs with credentials) refuses to promote leaky files;
  `--allow-secrets` overrides for one run.
- Multi-repo fanout:

  ```bash
  hornero sdd sync --workspace ~/repos   # syncs every child with .hornero/sdd.lock
  ```

## 9. Agent-facing wiki

```bash
hornero wiki init      # first full build (requires models.wiki)
hornero wiki update    # surgical refresh scoped by the git watermark
```

Set the model in config (`models: {wiki: fake:script.json}` for the MVP fake
backend; real providers arrive behind the same seam). Mechanics:

- `quickstart.md` is mandatory; sections: `architecture/ workflows/ domain/
  operations/`. Stub pages and broken relative links are rejected — nothing
  lands on failure.
- Updates analyze only the change window since the wiki watermark; an empty
  window never calls the model. The diff budget bounds edits (small windows
  touch at most 1-2 pages) and formatting-only edits are reverted.
- `.hornero/watermarks.json` (committed) records per-surface sync state for
  wiki, reports, reindex and gitsource; every surface says "already current"
  instead of rewriting identical bytes.

## 10. Code as signal (GitSource)

```yaml
# .hornero/config.yaml
signal_sources: [inbox, git]   # git is opt-in
```

Commits since the last reconcile watermark arrive as one digest signal
(messages + stats, redacted, never full diffs). Commits authored by hornero
identities are skipped. Evidence for git-sourced deltas cites verbatim
commit-message excerpts — the same mechanical check as inbox signals.

The reconciler also enforces a **delta budget**: at most 5 fresh deltas per
signal per run; the excess is queued in the ledger and re-presented next run.

## 11. Flight recorder & scribe

Every dispatch writes a redacted, sequenced event trace:

```bash
hornero runs list [--spec SPEC-002]
hornero runs show r-3-spec-002 --kind tool_use,error --range e#12:e#40
hornero runs adopt ~/.claude/session.jsonl    # adopt a Claude Code transcript
hornero runs prune --keep-days 90
```

The scribe distills a trace into a Decision Record (`sdd/decisions/DR-NNN`):

```bash
hornero scribe r-3-spec-002        # or automatic at dispatch close
                                   # when models.scribe is configured
```

Every DR claim carries an `[e#N-e#M]` citation that is mechanically
verified against the trace — unanchorable claims are dropped and logged,
and a trivial run yields no DR. DRs are indexed as knowledge: when a new
signal re-proposes an approach a past DR rejected, the HITL preview shows
`[memory] DR-NNN ...` before you decide.

## Exit codes

- `0` success · `1` operational failure (or unresolved diverged files in sync)
- `2` precondition/usage failure (no lock, unknown file, bad config)

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
  findings/ improvements/ evidence-backed improvement records and plans
  tasks/ state/ reviews/  SDD workflow state
```

Options:

- `--hooks` — also install a post-merge git hook that runs `hornero reindex`.
- `--print-ci-hook` — print a CI snippet for the same thing, write nothing.
- `--no-sdd` — skip the SDD-toolkit install step.

If `.hornero/config.yaml` sets `sdd_upstream`, `init` finishes by running
`hornero sdd install` against it. Without an upstream it just prints a hint —
init is offline-safe by default.

## 2. Create a project from a blueprint

```bash
hornero blueprint list
hornero new accounts-api --blueprint python-service --commit
hornero new console --blueprint fullstack --component docker
hornero blueprint status
```

Built-ins are `python-lib`, `python-service`, and `fullstack`. Components are
composed deterministically, variables are rendered through an allowlisted
template syntax, and destinations must be empty. The committed
`.hornero/blueprint.lock` records the blueprint/component versions and hashes;
`blueprint status` reports changed, missing, and current files but never
overwrites local edits.

## 3. Configuration (`.hornero/config.yaml`)

```yaml
signal_source: inbox          # SignalSource adapter
tracker: repo                 # TrackerPort adapter (spec files ARE the tracker)
dispatch:
  backend_order: [mock]       # 'api' is NEVER added automatically
  cli_command: []             # argv list; no shell interpolation
  timeout_seconds: 900
criterion_allowlist: [pytest, ruff, mypy, python]   # runnable acceptance criteria
models: {}                    # role -> fake:path or provider:name
providers: {}                 # explicit local-command or HTTP adapters
autonomy:
  enabled: false              # run stays disabled until explicitly enabled
  max_changes: 1
  allowed_risk: [low]
  gates: [[pytest, -q]]
sdd_upstream: ""              # toolkit source: git URL or local path
sdd_ref: main
```

Unknown keys fail closed with an error — typos never get silently ignored.

Real model routing is explicit. Credentials are read only from the configured
environment variable:

```yaml
models: {reconciler: provider:local, wiki: provider:remote}
providers:
  local:
    kind: command
    command: [my-local-model, --json]
    max_calls: 20
  remote:
    kind: openai_compatible
    base_url: https://provider.example/v1
    model: configured-model
    api_key_env: PROVIDER_API_KEY
    max_calls: 10
    max_tokens: 4096
    retries: 1
```

No provider is selected implicitly. Requests and responses are represented in
the audit log by hashes, not prompt bodies or credentials.

## 4. Feed and ingest signals

A signal is any markdown/text file dropped into `.hornero/inbox/`: meeting
notes, a Slack export, a customer email, a half-formed idea.

```bash
cp meeting-notes-2026-07-08.md .hornero/inbox/
hornero ingest requirements.docx architecture.html transcript.vtt
```

`ingest` supports text, Markdown, VTT, HTML, JSON, YAML and DOCX using the
standard library. PDF support is feature-detected through `pypdf` (`pip install
'hornero[documents]'`). Inputs are size-bounded, redacted, normalized to
Markdown and accompanied by a source-hash provenance sidecar.

## 5. Reconcile (signals → specs, with a human gate)

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

## 6. Build (approved specs → coding agents)

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

Both `reconcile` and non-empty `build` validate the existing graph before
making decisions. A stale or corrupt graph blocks with instructions to run
`hornero validate --repair`; this preflight never silently mutates knowledge.

## 7. Memory

```bash
hornero reindex               # rebuild .hornero/knowledge/ deterministically
hornero status                # includes index staleness
hornero knowledge query "where is dispatch implemented?"
hornero knowledge page file:hornero/build.py
hornero knowledge related file:hornero/build.py --rel references
hornero knowledge entity requirement:SPEC-005
hornero knowledge relations requirement:SPEC-005
hornero validate --repair
```

The knowledge layer indexes the full `sdd/` corpus, processed signals, and the
codebase. `hornero reindex` writes two local retrieval surfaces:

- `.hornero/knowledge/fallback/index.json` — deterministic token-overlap
  fallback over docs/signals.
- `.hornero/knowledge/graph/wiki.db` — a stdlib SQLite graph of file pages and
  semantic entities for sources, requirements, criteria, controls, tasks,
  decisions, symbols, tests and findings. Typed relations and provenance carry
  source hashes, generators, confidence and evidence locators. Queries use
  SQLite FTS5/BM25 when available and degrade locally.

Every graph DB refresh also writes `sdd/reports/knowledge-graph.html`, an
offline HTML report with graph counts, categories, edge relations, and page
samples. `open_knowledge()` prefers the local graph when present, then
feature-detected `parrot.knowledge.pageindex`, then the fallback index.

## 8. Reports

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

## 9. SDD toolkit sync

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

## 10. Agent-facing wiki

```bash
hornero wiki init      # first full build (requires models.wiki)
hornero wiki update    # surgical refresh scoped by the git watermark
```

Set the model in config (`models: {wiki: fake:script.json}` for deterministic
fixtures or `provider:name` for an explicitly configured provider). Mechanics:

- `quickstart.md` is mandatory; sections: `architecture/ workflows/ domain/
  operations/`. Stub pages and broken relative links are rejected — nothing
  lands on failure.
- Updates analyze only the change window since the wiki watermark; an empty
  window never calls the model. The diff budget bounds edits (small windows
  touch at most 1-2 pages) and formatting-only edits are reverted.
- `.hornero/watermarks.json` (committed) records per-surface sync state for
  wiki, reports, reindex and gitsource; every surface says "already current"
  instead of rewriting identical bytes.

## 11. Code as signal (GitSource)

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

## 12. Flight recorder & scribe

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

## 13. Continuous improvement

```bash
hornero improve scan
hornero improve plan --limit 20
hornero improve status --json
hornero improve run
hornero improve run --approve FIND-0123456789ab
```

`scan` validates/repairs derived graph state, runs deterministic policy packs,
and persists stable evidence-backed records in `sdd/findings/`. `plan` ranks up
to 20 open findings by severity, risk and confidence and writes
`sdd/improvements/plan.json`.

`run` is disabled by default. With `autonomy.enabled: true`, it executes at
most `max_changes`; only risks in `allowed_risk` are eligible. Medium/high risk
always additionally requires its exact `--approve FIND-ID`. Each change gets a
new `hornero/improve/<finding>` branch and temporary Git worktree, runs the
declared gates, commits only on success, removes failed branches, and records
the outcome in the SQLite ledger. It never pushes or merges the default branch;
successful findings remain `ready_for_review` until normal review/merge.

## 14. Temporal graph intelligence

```bash
hornero knowledge history requirement:SPEC-006
hornero knowledge analyze contradictions --json
hornero knowledge analyze duplicates --json
hornero knowledge impact requirement:SPEC-006 --depth 4
hornero knowledge coverage
hornero knowledge semantic-query --kind control --text security
hornero knowledge explain finding:FIND-0123456789ab
hornero knowledge context requirement:SPEC-006 --budget 1200
hornero extract requirements.md
```

Every reindex records an idempotent temporal snapshot in the ledger. Changed
entities create immutable versions and missing entities become inactive;
`history` never turns the derived graph into primary authority. Contradiction
and duplicate results are deterministic candidates with scores/evidence, not
automatic requirement decisions. `extract` requires `models.extractor` and
persists only proposed entities whose quoted evidence exists verbatim.

## 15. Registry, upgrades, contracts and workspaces

```bash
export HORNERO_REGISTRY_KEY='managed outside the repository'
hornero new accounts --blueprint company-service \
  --registry ./registry.json --registry-key-env HORNERO_REGISTRY_KEY
hornero blueprint resolve api database auth observability
hornero blueprint upgrade --dry-run
hornero blueprint upgrade --theirs Dockerfile
hornero contracts generate
hornero contracts check
hornero workspace graph ~/projects
hornero workspace plan ~/projects accounts/requirement:SPEC-101
```

Registry envelopes contain a canonical payload hash and HMAC signature; HTTPS
is mandatory for URLs. Blueprint lock schema 2 retains the generated base for
three-way upgrades. Diverged files block the entire preflight until explicitly
resolved with `--ours` or `--theirs`. The `production-service` blueprint
includes database/migrations, auth, queue, telemetry, containers, IaC, CI and a
single model that generates OpenAPI 3.1, event/data JSON schemas and a Python
client contract.

## 16. Assurance and policy packs

```bash
hornero improve baseline FIND-ID --status accepted_risk \
  --reason 'legacy exception' --owner security@example.com --expires 2026-12-31
hornero improve baseline-status
hornero assurance supply-chain --feed offline-vulnerabilities.json
hornero assurance threat-model
hornero assurance compliance iso27001
```

Baselines require an owner, reason and expiry; expired entries automatically
stop suppressing findings. Organization rules live in `sdd/policies/*.yaml`
with schema 1 and bounded literal matching. Assurance reports are written under
`sdd/reports/`; vulnerability data is used only when explicitly supplied.
Compliance output maps evidence and gaps but is never presented as a
certification or legal attestation.

## 17. Autonomous event runtime

```bash
hornero runtime init                  # writes disabled settings
hornero runtime emit scan
hornero runtime webhook event.json \
  --signature "$HMAC" --key-env HORNERO_WEBHOOK_KEY
hornero runtime tick
hornero runtime approve evt-3 --by owner@example.com
hornero runtime feedback FIND-ID --helpful --notes 'removed a real defect'
hornero runtime status --json
```

`.hornero/runtime.json` controls schedules, per-tick event/cost budgets,
retries, sandbox and PR configuration. Scheduled `run` refuses to execute
unless `.hornero/config.yaml` enables autonomy and provides
`autonomy.require_sandbox: true` plus a `sandbox_command`. Webhooks require
HMAC and a replay-safe delivery id. PR creation additionally requires
`allow_push`, event payload `allow_push: true`, and a named approval. Feedback
changes only a bounded rule-priority weight in `[0.5, 1.5]`; it cannot alter
risk, permissions, gates or approval policy.

## Exit codes

- `0` success · `1` operational failure (or unresolved diverged files in sync)
- `2` precondition/usage failure (no lock, unknown file, bad config)

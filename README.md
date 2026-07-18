# hornero 🪶

**Repo-native product loop**: requirement signals → living memory → SDD specs
→ dispatched builds → HTML reports. Everything lives in your git repo; nothing
needs a server, a database service, or a SaaS.

> El hornero (ovenbird) builds its own house, layer by layer — so does this
> tool: hornero is developed with the same spec-driven workflow it implements
> (fully self-hosting).

<!-- pypi-release-notes:start -->
## Latest changes

See the [changelog](CHANGELOG.md) for released and upcoming changes. Published
packages replace this block with the exact change set for that immutable PyPI
version.
<!-- pypi-release-notes:end -->

## What it does

```
 meeting notes, docs, ideas          you                     coding agents
        │                             │                            │
        ▼                             ▼                            ▼
 .hornero/inbox/  ──reconcile──▶  HITL review  ──apply──▶  sdd/specs/*.md
        │            (LLM drafts      approve/reject           │
        │             deltas with     /edit/skip               ▼
        │             VERBATIM        in your TTY         hornero build
        │             evidence)                          (spec → brief →
        │                                                 mock/cli backend)
        ▼                                                      │
 .hornero/knowledge/  ◀──reindex──  write-back: code + spec + reports
                                    land in the SAME branch/PR
        ▼
 sdd/reports/*.html   (capabilities, workflows, traceability — offline, deterministic)
```

- **Signals in**: drop meeting notes / docs into `.hornero/inbox/`.
- **Project factory**: create a Git repository and runnable stack from a
  composable, versioned blueprint; lock hashes expose local drift.
- **Reconcile**: an LLM drafts `RequirementDelta`s (NEW / CHANGED / OBSOLETE /
  DUPLICATE) — every delta carries evidence that is a *mechanically verified
  substring* of the source signal. No evidence, no delta.
- **Human gate**: nothing mutates a spec without an interactive approval
  (approve / reject / edit / skip). No TTY → no writes, by design.
- **Specs are the tracker**: markdown files with YAML frontmatter under
  `sdd/specs/`; status transitions and comments are written into the files
  themselves. ADRs in `sdd/decisions/`, low-confidence ideas become brainstorm
  proposals in `sdd/proposals/`.
- **Build**: approved specs are rendered into build briefs and dispatched to a
  coding-agent backend (`mock` by default; `cli`/`api` are explicit opt-ins).
- **Reports**: `capabilities.html`, `workflows.html`, `traceability.html` —
  the full audit chain signal → delta → spec → SDD tasks → PR → merge, with
  honest gaps.
- **SDD toolkit sync**: `hornero sdd install|status|diff|sync` manages your
  `.claude/` + `sdd/` toolkit files against an upstream repo with a committed
  lockfile and a three-way drift model — like a package manager for prompts,
  where **diverged files are never auto-merged**.
- **Agent-facing wiki**: `wiki/` is a second projection of the knowledge
  layer, written FOR the next agent run — watermark-scoped surgical updates,
  anti-stub and link-check gates, and a no-op discipline that makes scheduled
  refreshes churn-free (quiet days produce no PR).
- **Code as signal**: opt-in `GitSource` turns commits into requirement
  signals so specs and code never silently drift apart.
- **Flight recorder & scribe**: every dispatch leaves a redacted action-stream
  trace; the scribe distills it into a Decision Record whose every claim
  cites a verified event range — and past rejections resurface in the HITL
  preview before you approve a repeat.
- **Semantic project graph**: sources, requirements, criteria, controls, tasks,
  code, tests, decisions and findings are connected with source hashes and
  evidence locators. `validate` repairs derived state and fails closed on
  corrupt traceability.
- **Continuous improvement**: deterministic architecture, security,
  compliance, dependency, performance, quality, test, documentation and graph packs
  produce stable findings. Approved low-risk work runs in an isolated Git
  worktree; gates must pass before a review branch is retained.
- **Temporal intelligence**: immutable entity versions, supersession,
  contradiction/duplicate candidates, impact paths, coverage scores,
  explainable queries and token-budgeted context packs.
- **Production factory**: signed blueprint registries, three-way upgrades,
  capability resolution, production components, generated contracts and
  federated multi-repository plans.
- **Assurance**: expiring finding baselines, declarative policy packs, offline
  SBOM/vulnerability input, STRIDE threat models and evidence mappings for
  SOC 2, ISO 27001, GDPR and PCI.
- **Autonomous runtime**: signed webhook/schedule events, resource sandbox,
  budgets, retries, risk approvals, provider-neutral PR creation, metrics and
  bounded feedback learning. It never merges a branch.

## Install

Requires Python ≥ 3.11. Single runtime dependency (`pyyaml`).

```bash
git clone <this-repo> && cd hornero
python -m venv .venv && source .venv/bin/activate
uv pip install -e .            # or: pip install -e .
```

For ai-parrot's LLM-wiki knowledge plane and native Codex integration:

```bash
pip install 'hornero[knowledge]'
hornero wiki codex install
hornero wiki parrot build
```

## Quickstart

```bash
hornero new billing-api --blueprint python-service --commit
cd billing-api
hornero ingest product-requirements.docx
hornero reindex
hornero validate
hornero improve scan
hornero improve plan --limit 20
```

For an existing repository:

```bash
cd your-project/
hornero init                   # scaffolds .hornero/ + the sdd/ layout
echo "Users keep asking for CSV export of the usage table" \
  > .hornero/inbox/note-2026-07-08.md
hornero reconcile --dry-run    # see the proposed deltas, writes nothing
hornero reconcile              # review interactively, apply approved deltas
hornero build                  # dispatch approved specs (mock backend)
hornero reindex                # rebuild local knowledge graph + HTML graph report
hornero report                 # regenerate sdd/reports/*.html
hornero status                 # spec counts, inbox, index health
```

Add the shared SDD toolkit (agents, commands, rules, templates):

```bash
hornero sdd install --from <toolkit-repo-or-path>
hornero sdd status             # drift table: current/behind/modified/diverged/...
hornero sdd sync               # fast-forward what's safe; diverged blocks
```

## CLI at a glance

| Command | Purpose |
|---|---|
| `hornero new NAME [--blueprint NAME] [--component NAME]` | Create a Git repository and full Hornero/SDD stack from a versioned blueprint |
| `hornero init [--hooks] [--no-sdd]` | Scaffold `.hornero/` + `sdd/` layout (+ optional post-merge reindex hook) |
| `hornero blueprint list\|status` | List built-ins or report locked blueprint version and file drift |
| `hornero ingest FILE... [--kind KIND]` | Normalize supported documents into the inbox with provenance |
| `hornero validate [--repair] [--json]` | Validate graph schema, provenance, traceability and secret safety |
| `hornero improve scan\|plan\|run\|status` | Detect, prioritize, policy-gate, isolate, verify and ledger improvements |
| `hornero knowledge history\|analyze\|impact\|coverage\|semantic-query\|explain\|context` | Navigate temporal reasoning, impact and bounded agent context |
| `hornero extract FILE` | Propose graph entities from AI output with verbatim evidence gates |
| `hornero blueprint resolve\|upgrade` | Resolve capabilities or apply a signed three-way blueprint upgrade |
| `hornero contracts generate\|check` | Generate OpenAPI, event/data schemas and client contracts |
| `hornero workspace graph\|plan` | Federate repository graphs and calculate cross-repo impact |
| `hornero assurance supply-chain\|threat-model\|compliance` | Generate auditable security and compliance evidence reports |
| `hornero runtime init\|emit\|webhook\|tick\|approve\|feedback\|status` | Operate the bounded event runtime |
| `hornero status` | Spec counts by state, pending inbox, index health |
| `hornero reconcile [--dry-run]` | Poll signals → evidence-verified deltas → HITL → apply |
| `hornero build [SPEC-ID ...] [--backend mock\|cli]` | Approved specs → briefs → dispatch |
| `hornero reindex` | Rebuild `.hornero/knowledge/`: token index + code graph DB + `knowledge-graph.html` |
| `hornero knowledge query\|page\|related\|entity\|relations\|status` | Query file and semantic graph surfaces |
| `hornero report [--only NAME]` | Regenerate the HTML reports |
| `hornero sdd install --from SRC [--ref R] [--force]` | Install toolkit + scaffold + lockfile |
| `hornero sdd status` / `diff [FILE]` | Drift table / unified diff vs upstream |
| `hornero sdd sync [--dry-run] [--theirs F] [--ours F] [--force]` | Pull updates; diverged requires explicit resolution |
| `hornero sdd sync --push FILE...` | Promote improved files upstream via a PR (secret-scanned) |
| `hornero sdd sync --workspace DIR` | Pull-sync every child repo carrying `.hornero/sdd.lock` |
| `hornero sdd hold\|unhold\|pin FILE` | Per-file sync policy |
| `hornero wiki init\|update` | Agent-facing living wiki (watermark-scoped, no-op-disciplined) |
| `hornero wiki parrot build\|upsert\|query\|page\|related\|status\|export` | Operate ai-parrot's local LLM-wiki plane |
| `hornero wiki codex install\|status\|uninstall` | Manage query-first Codex instructions, skill and lifecycle hook |
| `hornero runs list\|show\|adopt\|prune` | Flight-recorder traces of every dispatch |
| `hornero scribe RUN [--force]` | Distill a trace into a Decision Record (verified citations) |

## Hard invariants

1. **Evidence is verbatim or the delta dies** — excerpts are mechanically
   verified substrings of the signal; mismatches are dropped and ledger-logged.
2. **HITL is fail-closed** — no approval channel ⇒ no spec mutation, no
   dispatch. `--dry-run` always leaves `git status` clean.
3. **No billed backend by surprise** — `api` never runs unless it is the
   explicit first entry of `dispatch.backend_order`.
4. **Diverged toolkit files are never auto-merged** — no timestamp heuristics;
   a human resolves with `--theirs` / `--ours` or by hand.
5. **Deterministic tests only** — the suite needs no network, keys, or
   services.

## Documentation

- [Usage guide](docs/USAGE.md) — the full loop, configuration, SDD toolkit sync
- [Development guide](docs/DEVELOPMENT.md) — setup, architecture, the self-hosted SDD workflow
- [Deployment guide](docs/DEPLOYMENT.md) — adopting hornero in your repos, CI, multi-repo fanout
- [PyPI release runbook](docs/RELEASING.md) — trusted automatic publishing from master
- [Changelog guide](docs/CHANGELOGS.md) — fragments, PR policy and PyPI projection
- [ai-parrot LLM-wiki guide](docs/PARROT_WIKI.md) — knowledge bridge and Codex integration
- [Changelog](CHANGELOG.md)
- [Visual artefacts](docs/artefacts/) — architecture diagram, infographic, cheatsheet, interactive onboarding (English + Spanish)

Specs are the source of truth: see `sdd/specs/`.

## License

[MIT](LICENSE)

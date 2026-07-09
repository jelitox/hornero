# hornero 🪶

**Repo-native product loop**: requirement signals → living memory → SDD specs
→ dispatched builds → HTML reports. Everything lives in your git repo; nothing
needs a server, a database service, or a SaaS.

> El hornero (ovenbird) builds its own house, layer by layer — so does this
> tool: hornero is developed with the same spec-driven workflow it implements
> (fully self-hosting).

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

## Install

Requires Python ≥ 3.11. Single runtime dependency (`pyyaml`).

```bash
git clone <this-repo> && cd hornero
python -m venv .venv && source .venv/bin/activate
uv pip install -e .            # or: pip install -e .
```

## Quickstart

```bash
cd your-project/
hornero init                   # scaffolds .hornero/ + the sdd/ layout
echo "Users keep asking for CSV export of the usage table" \
  > .hornero/inbox/note-2026-07-08.md
hornero reconcile --dry-run    # see the proposed deltas, writes nothing
hornero reconcile              # review interactively, apply approved deltas
hornero build                  # dispatch approved specs (mock backend)
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
| `hornero init [--hooks] [--no-sdd]` | Scaffold `.hornero/` + `sdd/` layout (+ optional post-merge reindex hook) |
| `hornero status` | Spec counts by state, pending inbox, index health |
| `hornero reconcile [--dry-run]` | Poll signals → evidence-verified deltas → HITL → apply |
| `hornero build [SPEC-ID ...] [--backend mock\|cli]` | Approved specs → briefs → dispatch |
| `hornero reindex` | Rebuild the deterministic knowledge index |
| `hornero report [--only NAME]` | Regenerate the HTML reports |
| `hornero sdd install --from SRC [--ref R] [--force]` | Install toolkit + scaffold + lockfile |
| `hornero sdd status` / `diff [FILE]` | Drift table / unified diff vs upstream |
| `hornero sdd sync [--dry-run] [--theirs F] [--ours F] [--force]` | Pull updates; diverged requires explicit resolution |
| `hornero sdd sync --push FILE...` | Promote improved files upstream via a PR (secret-scanned) |
| `hornero sdd sync --workspace DIR` | Pull-sync every child repo carrying `.hornero/sdd.lock` |
| `hornero sdd hold\|unhold\|pin FILE` | Per-file sync policy |
| `hornero wiki init\|update` | Agent-facing living wiki (watermark-scoped, no-op-disciplined) |
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
- [Changelog](CHANGELOG.md)

Specs are the source of truth: see `sdd/specs/`.

## License

[MIT](LICENSE)

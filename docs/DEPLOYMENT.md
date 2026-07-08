# Deployment guide

Hornero is repo-native: there is **no server, daemon, database service or
registry to deploy**. "Deploying" means installing the CLI where it runs and
adopting the loop in each repository. Everything it writes is either committed
(specs, ADRs, reports, `sdd.lock`) or a local gitignored runtime
(`.hornero/ledger.db`, caches, knowledge index).

## 1. Install the CLI

Per user (recommended):

```bash
pipx install <path-or-git-url-to-hornero>     # or: uv tool install
# or inside a project venv:
uv pip install <path-or-git-url-to-hornero>
```

Requirements: Python ≥ 3.11, `git` on PATH. `gh` (GitHub CLI) is needed only
for `sdd sync --push`; its absence is reported cleanly, never a traceback.

Optional knowledge upgrade: installing `ai-parrot` makes
`parrot.knowledge.pageindex` / `graphindex` available and hornero picks them
up automatically; without it, the deterministic token-overlap fallback is used.

## 2. Adopt in a repository

```bash
cd the-repo/
hornero init                       # idempotent; never overwrites config
git add -A && git commit -m "chore: adopt hornero"
```

`init` also appends `.hornero/ledger.db*` to `.gitignore`. Commit the `sdd/`
skeleton and `.hornero/config.yaml`; runtime state stays out of git.

### With a shared SDD toolkit

Point the repo at your toolkit upstream (a git URL or a local checkout):

```yaml
# .hornero/config.yaml
sdd_upstream: git@github.com:you/sdd-toolkit.git
sdd_ref: main
```

Then `hornero init` (or `hornero sdd install`) installs the managed set and
writes `.hornero/sdd.lock` — **commit the lock**: it is the repo's sync
identity. Already hand-copied toolkit files are adopted, not clobbered:
identical files lock as `current`, edited ones as `modified`.

Remote upstreams are cached as a shallow blobless clone under
`.hornero/cache/sdd-upstream/` and refreshed on each status/sync; when the
network is down, commands degrade to the cache with a staleness warning
instead of failing.

## 3. Keep memory fresh (hooks / CI)

Local git hook (opt-in):

```bash
hornero init --hooks               # post-merge → hornero reindex
```

CI variant:

```bash
hornero init --print-ci-hook       # prints the snippet, writes nothing
```

Reindex is deterministic, so running it in CI after merges keeps
`.hornero/knowledge/` reproducible for every checkout.

## 4. Operating routine

A healthy cadence per repo:

```bash
hornero status                     # anything pending?
hornero reconcile                  # human-gated; requires a TTY by design
hornero build && hornero report
hornero sdd sync --dry-run         # what would toolkit sync do?
hornero sdd sync
```

Notes for operators:

- `reconcile` **cannot run unattended**: with no TTY it exits without writing
  (fail-closed HITL). Do not try to script around this — it is the product's
  core safety property.
- `sync` exits non-zero while any `diverged` file lacks an explicit
  `--theirs`/`--ours` resolution. Treat that exit code as "a human decision is
  pending", not as an error to retry.
- The dispatch backend order lives in config. Keep `[mock]` until you
  deliberately wire a real coding-agent CLI (`cli` uses your own session
  auth). `api` only ever runs as an explicit first entry — never deploy a
  config you did not intend to bill.

## 5. Multi-repo (workspace) fanout

For a directory of adopted repos:

```bash
hornero sdd sync --workspace ~/work/repos
```

Only immediate children containing `.hornero/sdd.lock` are touched — each is
pull-synced against **its own** lock identity; everything else is skipped and
counted in the summary. The exit code is the worst child result, so a single
diverged repo makes the fanout visibly non-green.

## 6. Promoting toolkit improvements

When a repo improves a managed file (state `modified`):

```bash
hornero sdd sync --push .claude/commands/sdd-start.md
```

This creates branch `sdd-toolkit/promote-<repo>` on the upstream checkout,
commits the file(s), pushes, and opens a PR via `gh` — it never pushes the
upstream default branch. A secret scan (AWS keys, GitHub tokens, `sk-` keys,
bearer tokens, private-key blocks, URLs with embedded credentials) refuses
leaky files; `--allow-secrets` overrides for a single run when the match is a
false positive.

## 7. Backup / reset

- Everything durable is in git (specs, ADRs, reports, lock, config).
- `.hornero/ledger.db` is the local audit trail; losing it loses run history
  but no product state.
- Safe reset of runtime state: delete `.hornero/knowledge/` and
  `.hornero/cache/`, then `hornero reindex`.

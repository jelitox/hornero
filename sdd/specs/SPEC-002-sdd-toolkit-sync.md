---
spec: SPEC-002
title: Hornero SDD toolkit — install, memory bootstrap, and cross-repo sync
status: proposed
kind: new_feature
created: 2026-07-06
owner: javier@javierleon.dev
depends_on: [SPEC-001]
amends: [SPEC-001]
---

# SPEC-002 — SDD toolkit: install, memory bootstrap, and cross-repo sync

## 1. Context

The SDD methodology (WORKFLOW.md, slash commands, subagents, rules, skills,
templates) currently lives inside `ai-parrot` and is copied by hand into other
repos, where copies silently drift. Hornero becomes the distribution and sync
mechanism: drop Hornero into **any** repo and it (a) installs the SDD toolkit,
(b) scaffolds the SDD state layout, (c) builds a knowledge memory of the whole
repo, and (d) keeps the toolkit synchronized across every repo that uses it —
in both directions.

### 1.1 The managed set (toolkit inventory, as of upstream today)

Synced across repos — the **toolkit**:

```
.claude/agents/        code-reviewer, product-analyst, qa-runner,
                       sdd-autopilot, sdd-qa, sdd-research, sdd-worker
.claude/commands/      pr-review, product-analyst, user-story,
                       sdd-brainstorm, sdd-proposal, sdd-spec, sdd-task,
                       sdd-start, sdd-next, sdd-status, sdd-done,
                       sdd-codereview, sdd-explain, sdd-fromjira,
                       sdd-tojira, sdd-insight
.claude/rules/         python-development, rust-development,
                       cython-development, using-git-worktrees,
                       worktree-start-feature, worktree-status,
                       worktree-pr-and-clean
.claude/skills/        meta-prompting/ (5 SKILL.md files)
.claude/workflows/     sdd-insight.js
sdd/WORKFLOW.md
sdd/templates/         brainstorm, proposal, spec, task, finding,
                       research_plan.prompt, synthesis.prompt
```

Never synced — **repo-local state**:

```
sdd/proposals/   sdd/specs/   sdd/state/   sdd/tasks/{active,completed,index}/
sdd/reviews/     sdd/migrations/
```

The exact managed set is defined by the upstream manifest (§4), not hardcoded
in Hornero — the inventory above is today's snapshot, not the contract.

## 2. Amendment to SPEC-001

**SPEC-001 §4 repo layout is amended: `product/specs/` and `product/decisions/`
are dropped.** Hornero adopts the SDD layout as its native spec store:

- The reconciler's `NEW` deltas produce `sdd/proposals/<slug>.brainstorm.md`
  (using `sdd/templates/brainstorm.md`) or, when confidence and evidence
  support it, scaffold `sdd/specs/<slug>.spec.md` directly.
- `CHANGED` deltas patch the existing `sdd/specs/*.spec.md`.
- `hornero build` translates an approved spec into a brief whose dispatch payload
  invokes the SDD machinery itself (`/sdd-task` decomposition + `sdd-worker`
  execution + `sdd-codereview` gate) via the `DispatchPort` — Hornero does not
  reinvent a task lifecycle that `sdd/tasks/index/*.json` already implements.
- ADRs and reports live in `sdd/decisions/` and `sdd/reports/` (new,
  repo-local, created by `hornero init`).
- The knowledge layer (`hornero reindex`) indexes the full `sdd/` corpus — specs,
  proposals, findings under `sdd/state/*/findings/`, synthesis files — plus
  `.hornero/processed/` signals and the source tree. Installing Hornero in a repo
  with an existing SDD history bootstraps a rich memory on day one.

Everything else in SPEC-001 (ports, `RequirementDelta`, HITL, ledger,
`.hornero/`) stands.

## 3. Goals

- G1. `hornero sdd install` makes any repo SDD-capable in one command: toolkit
  files + state skeleton + lockfile.
- G2. `hornero sdd sync` propagates toolkit updates across repos with three-way
  awareness: never silently clobber local modifications.
- G3. Bidirectional: improvements made in any repo can be promoted upstream
  (`sync --push`), so the toolkit evolves from real usage instead of drifting.
- G4. `hornero sdd status` shows drift per file: current, behind, modified,
  diverged.
- G5. The toolkit upstream is configurable — today `phenobarbital/ai-parrot`
  subpaths; later a dedicated `sdd-toolkit` repo without changing Hornero.

## 4. Upstream contract — manifest

The upstream repo carries `sdd-toolkit.manifest.json` at its root (or a
configured subpath). If absent (bootstrap period, ai-parrot has none yet),
Hornero falls back to a built-in path-pattern manifest matching §1.1 and warns.

```json
{
  "name": "sdd-toolkit",
  "version": "2026.07.0",
  "managed": [
    ".claude/agents/*.md",
    ".claude/commands/*.md",
    ".claude/rules/*.md",
    ".claude/skills/meta-prompting/**/SKILL.md",
    ".claude/workflows/sdd-insight.js",
    "sdd/WORKFLOW.md",
    "sdd/templates/*.md"
  ],
  "scaffold": [
    "sdd/proposals/", "sdd/specs/", "sdd/state/",
    "sdd/tasks/active/", "sdd/tasks/completed/", "sdd/tasks/index/",
    "sdd/reviews/", "sdd/decisions/", "sdd/reports/"
  ]
}
```

`version` is CalVer (`YYYY.MM.patch`); the lockfile additionally records the
exact upstream commit SHA, which is the real identity.

## 5. Per-repo lockfile — `.hornero/sdd.lock`

Written by `install` and every successful `sync`:

```json
{
  "upstream": "https://github.com/phenobarbital/ai-parrot.git",
  "upstream_ref": "main",
  "toolkit_version": "2026.07.0",
  "upstream_commit": "<sha>",
  "synced_at": "2026-07-06T14:00:00Z",
  "files": {
    ".claude/commands/sdd-start.md": {
      "upstream_hash": "<sha256>",
      "installed_hash": "<sha256>",
      "policy": "sync"
    },
    ".claude/rules/python-development.md": {
      "upstream_hash": "<sha256>",
      "installed_hash": "<sha256>",
      "policy": "local"
    }
  }
}
```

`policy` per file: `sync` (default) | `local` (repo opted out — never
overwritten, never pushed) | `pinned` (frozen at a specific upstream hash).
Policies are set via `hornero sdd hold <file>` / `unhold` / `pin`.

## 6. Drift model (three-way)

For each managed file, compare three hashes — U (upstream now), L (lockfile
`installed_hash`, i.e. last sync), C (current file on disk):

| U vs L | C vs L | State | `sync --pull` action |
|---|---|---|---|
| same | same | **current** | nothing |
| differs | same | **behind** | fast-forward: copy upstream, update lock |
| same | differs | **modified** | nothing; candidate for `--push` |
| differs | differs | **diverged** | STOP: show diff, require `--theirs` / `--ours` / manual merge |
| — | file missing | **deleted locally** | reinstall only with `--force`; otherwise report |
| new in U | — | **new upstream** | install, update lock |

Hard rule: **diverged files are never auto-resolved.** No timestamp
heuristics, no "newest wins". The human resolves, mirroring the HITL
philosophy of SPEC-001.

## 7. CLI surface

```
hornero sdd install [--from <git-url|path>] [--ref <branch|tag|sha>]
hornero sdd status                       # drift table, one line per managed file
hornero sdd diff [<file>]                # upstream vs local unified diff
hornero sdd sync [--pull] [--dry-run]    # pull is the default direction
hornero sdd sync --push [<file>...]      # promote modified files upstream
hornero sdd hold|unhold|pin <file>
```

Mechanics:

- Upstream access: shallow sparse clone into `.hornero/cache/sdd-upstream/`
  (exactly the `--filter=blob:none --sparse` pattern), refreshed on each
  `status`/`sync`. Works offline against the cache with a staleness warning.
- `install` refuses to overwrite existing files unless `--force`; on a repo
  that already has hand-copied SDD files, it adopts them: hashes each file,
  marks matches as `current` and mismatches as `modified` (not clobbered).
- `sync --push` creates a branch on the upstream clone, commits the promoted
  files, and opens a PR via `gh` (title `sdd-toolkit: promote <file> from
  <repo>`). It never pushes to the upstream default branch directly.
- Multi-repo fanout is just the loop the user runs; a convenience
  `hornero sdd sync --workspace <dir>` iterates over every child repo containing
  `.hornero/sdd.lock`. No daemon, no central registry.

## 8. Interaction with the product loop (SPEC-001)

- `hornero init` now runs `hornero sdd install` as its final step (skippable with
  `--no-sdd`), so a fresh repo gets loop + toolkit + memory in one command.
- `hornero reconcile` writes into the SDD layout (§2), so approved requirement
  deltas are immediately actionable by `/sdd-task` in Claude Code — the human
  can drive the next phase manually or let `hornero build` dispatch it.
- The traceability report gains a column: signal → delta → proposal/spec →
  SDD task ids (`sdd/tasks/index/<slug>.json`) → PR → merge.
- `hornero reindex` treats `sdd/state/*/findings/` as first-class knowledge:
  research findings from past features are exactly the episodic memory the
  reconciler needs to avoid re-proposing settled questions.

## 9. Phases (extends SPEC-001 §12)

| Phase | Deliverable | Gate (deterministic) |
|---|---|---|
| **F2.5 — sdd install** | manifest reader + fallback patterns, sparse-clone cache, installer, lockfile, scaffold | on a fixture upstream: `install` produces the managed set + skeleton, lock hashes verify; re-run is idempotent (git diff empty) |
| **F3.5 — sdd sync** | three-way drift engine, `status`/`diff`/`sync --pull`, hold/pin | fixture matrix covering all six drift states resolves per §6 table; diverged file blocks with exit code ≠ 0 |
| **F4.5 — sdd push** | `sync --push` PR flow, `--workspace` fanout | mock `gh`: push creates branch + PR payload with expected files; workspace loop touches only repos with a lockfile |

F2.5 is deliberately early: `install` + memory bootstrap is the single most
useful thing Hornero can do on day one for the "implant in any repo" goal, and it
has zero LLM dependency.

## 10. Risks

- **R6. Manifest drift** — upstream restructures paths (cf. FEAT-198 import
  moves). Mitigation: manifest lives upstream, versioned with the files it
  describes; Hornero only falls back to built-in patterns when it is absent.
- **R7. Prompt-content merge conflicts** — command files are prose; textual
  merges are riskier than code merges. Mitigation: §6 never auto-merges;
  `diff` renders side-by-side for human resolution.
- **R8. Push-noise upstream** — every repo promoting tweaks floods the toolkit
  repo. Mitigation: push is per-file, explicit, and PR-gated; nothing is
  promoted implicitly.
- **R9. Secret leakage via push** — a locally modified command could embed
  repo-specific tokens/URLs. Mitigation: push runs a secret-pattern scan and
  refuses on match (allowlist override per run).

## 11. Open questions

- OQ5. Should `sdd-insight` telemetry aggregate cross-repo (a `--workspace`
  rollup)? Natural F5+ extension; deferred.
- OQ6. When does the toolkit graduate from ai-parrot subpaths to its own
  `sdd-toolkit` repo? Hornero is agnostic (`--from`), but the manifest should be
  born in whichever repo is canonical. Proposal: keep ai-parrot as upstream
  until the first non-T-ROC-adjacent repo adopts it.
- OQ7. Rules are language-specific (`python-development`, `rust-development`).
  Should the manifest support profiles (`--profile python`) so a Rust-only
  repo doesn't get Python rules? Leaning yes, F3.5.

## Log

- 2026-07-06 — Spec drafted (status: proposed). Toolkit inventory captured
  from phenobarbital/ai-parrot @ main.

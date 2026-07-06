# CLAUDE.md — hornero

Repo-native product loop agent. Ingests requirement signals (meeting notes,
docs) into `.hornero/inbox/`, reconciles them against SDD specs with verbatim
evidence, dispatches approved specs to coding agents, and writes code + specs
+ ADRs + HTML reports back into the same repo. The ovenbird builds its own
house, layer by layer.

## Source of truth

- `sdd/specs/SPEC-001-hornero-foundation.md` — ports, RequirementDelta,
  spec lifecycle, repo layout, phases F1–F5.
- `sdd/specs/SPEC-002-sdd-toolkit-sync.md` — `hornero sdd` install/sync/push,
  drift model, phases F2.5/F3.5/F4.5. Amends SPEC-001 §4 (SDD layout is native).
- `sdd/WORKFLOW.md` — the SDD methodology this repo follows for its own
  development. This project is self-hosting: hornero is built with the same
  spec/task lifecycle it implements.

When a spec and this file disagree, the spec wins; flag the discrepancy in
the task log instead of silently picking one.

## Environment

```bash
source .venv/bin/activate          # ALWAYS, before any python/uv/pip command
uv pip install -e '.[dev]'         # first time
pytest -q                          # test suite
ruff check . && mypy hornero       # lint gates
```

Python >= 3.11. `uv` for everything; never bare `pip`.

## Hard invariants (violations are bugs, never "acceptable for now")

1. **Evidence is verbatim or the delta dies.** Every `RequirementDelta`
   carries >= 1 `Evidence` whose `excerpt` is a mechanically verified
   substring of the source signal. Non-matching drafts are dropped and
   ledger-logged (`evidence_mismatch`), never "fixed".
2. **HITL is fail-closed.** No approval channel => no spec mutation, no
   dispatch, no exception. `--dry-run` must leave `git status` clean.
3. **No billed backend by surprise.** Dispatch goes through
   `multicoders.backends`; `ApiBackend` is opt-in only, never a fallback.
   Never proxy, pool, or redistribute subscription tokens (CliBackend
   BYO-auth constraint is inherited and absolute).
4. **Diverged toolkit files are never auto-merged** (SPEC-002 §6). No
   timestamp heuristics.
5. **Knowledge layers are feature-detected.** `parrot.knowledge.pageindex` /
   `graphindex` may be absent; the token-overlap fallback is a first-class
   code path with its own tests, not a stub. Import path is
   `parrot.knowledge.pageindex` (post-FEAT-198), never `parrot.pageindex`.
6. **Deterministic tests only.** No test may require network, LLM keys,
   Redis, or Jira. Real-engine + simulated-externals is the pattern
   (`FakeLLM`, `MockBackend`, fixture inboxes) — mirror
   ai-parrot's `examples/dev_loop/e2e_demo.py` philosophy.

## Phase gates (definition of done)

A phase is done ONLY when its gate from the spec passes, verbatim:

- **F1**: `pytest tests/test_lifecycle.py tests/test_inbox.py -q` green;
  `hornero init && hornero status` exit 0 on an empty repo.
- **F2**: fixture inbox (3 notes) -> expected delta set with `FakeLLM`;
  every delta evidence-verified; `--dry-run` leaves git diff empty.
- **F2.5**: fixture upstream -> `hornero sdd install` produces managed set +
  skeleton, lock hashes verify, re-run idempotent.
- **F3**: approved fixture spec -> mock backend -> status transitions
  `approved -> building -> review`, fake PR URL in ledger.
- **F3.5**: drift matrix (all 6 states) resolves per SPEC-002 §6 table;
  diverged blocks with exit code != 0.
- Later gates: see the specs.

Do not start phase N+1 with phase N's gate red.

## Workflow

Development follows the repo's own SDD commands:

1. `/sdd-task sdd/specs/SPEC-001-hornero-foundation.md` — decompose into
   task artifacts (respect phase ordering: F1 tasks first, F2.5 may
   interleave after F1).
2. `/sdd-next` / `/sdd-start TASK-NNN` — execute; one task per worktree if
   parallelizing (see `.claude/rules/using-git-worktrees.md`).
3. `/sdd-codereview` gate before marking done; `/sdd-status` for the board.

Commits: conventional (`feat:`, `fix:`, `chore:`, `test:`), one logical
change each. Git identity: personal (`javier@javierleon.dev`) — this is an
open-source personal project, NOT a T-ROC repo. No T-ROC/Navigator
internals, hostnames, or Jira keys may appear in code, tests, or fixtures.

## Layout

```
hornero/            package: cli.py, ports.py, lifecycle.py, reconciler/,
                    memory/, sdd_toolkit/, reports/
tests/              deterministic suite + fixtures/
sdd/                the SDD corpus (this repo's own specs/tasks/state)
.hornero/           runtime: inbox/, processed/, knowledge/, ledger.db (gitignored)
.claude/            SDD toolkit (managed set — will be governed by SPEC-002)
```

## When in doubt

- Ambiguity in a spec -> record an OQ in the spec's `## Log` and pick the
  most conservative interpretation (the one that mutates less state).
- Missing capability in a pinned dependency -> feature-detect + fallback,
  never hard-require.
- Anything touching approval flows, token handling, or destructive git
  operations -> stop and ask; do not proceed autonomously.

# Development guide

## Setup

```bash
git clone <this-repo> && cd hornero
python -m venv .venv
source .venv/bin/activate        # ALWAYS, before any python/uv/pip command
uv pip install -e '.[dev]'
```

Python ≥ 3.11. `uv` for package management, never bare `pip`.

## Quality gates

```bash
pytest -q                        # full deterministic suite
ruff check .                     # lint
mypy hornero                     # types
```

All three must be green before a task is done — no exceptions. The suite is
**deterministic by contract**: no test may require network, LLM keys, Redis,
or external services. The pattern is *real engine + simulated externals*
(`FakeLLM`, `MockBackend`, fixture inboxes, `RecordingRunner`, `block_network`).

## Architecture map

```
hornero/
  cli.py               argparse surface; thin — every command delegates
  config.py            .hornero/config.yaml, fail-closed on unknown keys
  layout.py            single resolver for the sdd/ layout paths
  ports.py             Protocols: Signal, SignalSource, TrackerPort, DispatchPort
  models.py            RequirementDelta + Evidence (verbatim-substring check)
  lifecycle.py         SpecDoc / SpecCorpus / status machine; specs ARE the tracker
  criteria.py          runnable acceptance criteria (allowlisted commands)
  hooks.py             post-merge reindex hook + CI snippet
  adapters/
    inbox.py           filesystem SignalSource (.hornero/inbox → processed)
    repo_tracker.py    TrackerPort writing transitions/comments into spec files
    dispatch.py        BuildBrief rendering + backend resolution (mock/cli/api)
  reconciler/
    run.py             the reconcile pipeline (poll → draft → verify → gate → apply)
    drafts.py          LLM drafting seam (FakeLLM in tests)
    hitl.py            TerminalChannel; fail-closed when no TTY
    apply.py           the ONLY writer of sdd/specs in the pipeline
  memory/
    ledger.py          SQLite audit ledger (runs, deltas, dispatches, signals)
    knowledge.py       pageindex/graphindex feature-detect + token-overlap fallback
    reindex.py         deterministic index build; staleness reporting
  reports/
    engine.py          shared context, HTML skeleton, deterministic rendering
    capabilities.py / workflows.py / traceability.py
  sdd_toolkit/
    manifest.py        upstream manifest + builtin fallback patterns
    upstream.py        local-dir or shallow-clone cache fetch (offline-tolerant)
    lock.py            .hornero/sdd.lock model (hashes + policies)
    install.py         install/adopt/scaffold, idempotent
    drift.py           three-way drift engine (§6) — classify + apply_pull
    cli_sync.py        status/diff/sync/hold/pin (thin over drift.py)
    push.py            --push PR flow (secret scan, runner seam) + --workspace
tests/                 one file per surface; fixtures inline
sdd/                   this repo's own specs/tasks/state (self-hosting)
```

Two specs govern everything: `sdd/specs/SPEC-001-hornero-foundation.md`
(ports, delta model, lifecycle, phases F1–F5) and
`sdd/specs/SPEC-002-sdd-toolkit-sync.md` (toolkit install/sync/push, drift
model, phases F2.5/F3.5/F4.5). **When code and spec disagree, the spec wins**;
record the discrepancy instead of silently picking one.

## Hard invariants (violations are bugs, never "acceptable for now")

1. Evidence is verbatim or the delta dies.
2. HITL is fail-closed: no approval channel ⇒ no writes; `--dry-run` leaves
   `git status` clean.
3. No billed backend by surprise; never proxy/pool subscription tokens.
4. Diverged toolkit files are never auto-merged. No timestamp heuristics.
5. Knowledge layers are feature-detected; the fallback is a first-class path.
6. Deterministic tests only.

## The SDD workflow (this repo is self-hosting)

Development follows the same spec/task lifecycle hornero implements:

1. **Spec** — brainstorm → proposal → `sdd/specs/SPEC-NNN-<slug>.md`
   (`/sdd-brainstorm`, `/sdd-spec`). Ambiguity? Record an OQ in the spec's
   `## Log` and pick the interpretation that mutates less state.
2. **Decompose** — `/sdd-task <spec>` produces task files under
   `sdd/tasks/active/` plus a JSON index in `sdd/tasks/index/`. Tasks carry a
   *Codebase Contract* section (verified imports/paths — anti-hallucination).
3. **Execute** — `/sdd-next` or `/sdd-start TASK-NNN`. One task per worktree
   when parallelizing.
4. **Gate** — a phase is done ONLY when its gate from the spec passes
   verbatim (F1–F5, F2.5, F3.5, F4.5). Never start phase N+1 with phase N red.
5. **Close** — fill the task's Completion Note (including deviations), move
   it to `sdd/tasks/completed/`, update the index JSON, commit.

Commits: conventional (`feat:`/`fix:`/`chore:`/`test:` + task id), one logical
change each. Git identity is personal (`javier@javierleon.dev`) — this is an
open-source personal project.

## Adding a new adapter (the intended extension seam)

- New signal source → implement `SignalSource` (`poll() → list[Signal]`,
  `ack(signal_id)`) in `adapters/`, register in config.
- New tracker → implement `TrackerPort` (`transition`, `comment`).
- New dispatch backend → keep `dispatch()` non-raising for operational
  failures; return `failed`/`needs_human` with a written log. Remember: `api`
  must stay opt-in only.
- New report → a `generate(ctx) → str` module under `reports/`, registered in
  `reports/run.py`; must stay offline + deterministic.

## Testing conventions

- Fixture repos are built inline per test (`tmp_path`), incl. `git init` when
  porcelain checks matter.
- CLI is exercised through `hornero.cli.main([...])` — never subprocess.
- Anything that could hit the network is seamed (runner injection for
  `git push`/`gh`, `block_network` fixture for reports).
- Determinism checks compare bytes across runs.

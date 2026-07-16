# Code review: hornero

Date: 2026-07-14
Reviewer: Codex
Scope: `/home/jelitox/int/jelitox/repos/hornero`

## Findings

### High: toolkit manifest paths can write outside the target repository

`load_manifest()` accepts `managed` and `scaffold` entries as strings without
path validation (`hornero/sdd_toolkit/manifest.py:66-72`). `install()` then
uses those values directly:

- `scaffold_dirs()` builds `repo_root / rel`, calls `mkdir(parents=True)`, and
touches `.gitkeep` (`hornero/sdd_toolkit/install.py:29-33`).
- Managed files are copied to `repo_root / rel` (`hornero/sdd_toolkit/install.py:57-63`).
- Sync resolution similarly writes to `root / rel` (`hornero/sdd_toolkit/cli_sync.py:94-97`).

Impact: installing or syncing from a malicious or compromised toolkit upstream
can create or overwrite paths outside the repo via absolute paths or `..`
segments, depending on the path surface. The CLI accepts a git URL or local path
as upstream, so this is a real trust-boundary issue.

Recommended fix: centralize manifest/lock path validation. Reject absolute
paths, empty paths, `..` segments, and paths whose resolved destination is not
inside `repo_root`. Apply the same validation to `managed`, `scaffold`, lockfile
entries, `--theirs`, `--ours`, `hold`, `unhold`, `pin`, `diff`, and push file
arguments. Add tests with malicious `scaffold: ["../outside"]` and managed/lock
entries containing `..`.

### Medium: `hornero build` can leave a spec in `building` before dispatch exists

`run_build()` transitions the spec to `building` and writes a tracker comment
before `brief_from_spec()` validates acceptance criteria
(`hornero/build.py:88-95`). `brief_from_spec()` calls `parse_criteria()`, which
raises on an empty criterion (`hornero/adapters/dispatch.py:36-43` and
`hornero/criteria.py`). `tests/test_dispatch.py` covers that `brief_from_spec`
raises, but the build e2e tests do not cover the full command behavior after the
pre-dispatch mutation.

Impact: a malformed approved spec can make `hornero build` abort after mutating
the spec to `building`, before `record_dispatch()`, `record_agent_run()`, or
`finish_run()`. The repo is left in a misleading in-progress state with an
unfinished ledger run and no trace explaining the failure.

Recommended fix: create and validate all `BuildBrief`s before any tracker
transition, or catch pre-dispatch validation exceptions and transition the spec
to `needs_human` with a comment and ledger closure. Add an e2e test for an
approved spec containing a blank acceptance criterion.

### Low: queued deltas can be re-presented forever in fail-closed runs

Queued deltas are revived from rows with `status='queued'`
(`hornero/reconciler/run.py:136-141`). In `--dry-run` and no-TTY paths, every
revived delta is recorded back as `proposed` (`hornero/reconciler/run.py:181-199`),
which consumes the queue by replacing the same `delta_id`. With a real channel,
decisions also consume the queue, and that path is tested in
`tests/test_gitsource.py`.

The untested edge is operational: if a queued delta is re-presented in a
non-interactive automation run and there are also new excess deltas, the command
can continue to create fresh queued rows while no human approval is possible.
That does not violate fail-closed mutation safety, but it can create repeated
review debt and noisy ledger state in scheduled runs.

Recommended fix: make queue state explicit rather than overloading `proposed`
for non-interactive re-presentation. For example, keep revived queued deltas as
`queued` when there is no approval channel, or add a `last_presented_run_id`
field and a test for no-TTY re-presentation with queued plus fresh excess
deltas.

## Positive observations

- The project has strong deterministic coverage: 234 tests passed.
- `ruff` and `mypy` are clean in the repo's `.venv`.
- The code consistently uses seams for LLMs, subprocess runners, dispatch
backends, and network-sensitive operations.
- Core invariants are encoded in tests and in runtime checks: evidence
verification, HITL fail-closed behavior, API opt-in dispatch, diverged toolkit
blocking, and deterministic reports.

## Verification

Commands run from `/home/jelitox/int/jelitox/repos/hornero`:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy hornero
```

Results:

- `234 passed in 3.75s`
- `All checks passed!`
- `Success: no issues found in 46 source files`

## Residual risk

This was a static review plus local gates. I did not execute malicious upstream
fixtures or patch the findings in this pass. The highest-priority follow-up is a
path-containment hardening patch for `sdd_toolkit` plus regression tests.

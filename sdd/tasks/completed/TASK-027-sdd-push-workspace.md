# TASK-027: `sync --push` PR flow + `--workspace` fanout (F4.5 gate closer)

**Feature**: SPEC-002 — SDD toolkit: install, memory bootstrap, and cross-repo sync
**Spec**: `sdd/specs/SPEC-002-sdd-toolkit-sync.md`
**Status**: done
**Priority**: medium
**Estimated effort**: L (4-8h)
**Depends-on**: TASK-026
**Assigned-to**: unassigned

---

## Context

SPEC-002 G3: improvements promote upstream via per-file, explicit,
PR-gated pushes — never direct to the default branch (§7). R9: a
secret-pattern scan refuses to promote files that embed tokens. **Closes
the F4.5 phase gate** (and SPEC-002's scope): mock `gh` receives branch +
PR payload with the expected files; the workspace loop touches only repos
carrying a lockfile.

## Scope

- `hornero/sdd_toolkit/push.py`:
  - `push(repo_root, files, *, runner, echo, allow_secrets=False) -> int`:
    1. Validate each file is state MODIFIED (only modified files are
       promotable; anything else ⇒ exit ≠ 0 listing offenders).
    2. **Secret scan (R9)**: regex set (AWS keys, `ghp_`/`github_pat_`,
       `sk-`-style, `Bearer <long>`, private-key headers, URLs with
       userinfo). Match ⇒ refuse (exit ≠ 0) unless `--allow-secrets`.
    3. In the upstream cache clone: create branch
       `sdd-toolkit/promote-<repo-name>`, copy files, commit, and via the
       injected `runner` (subprocess in prod, mock in tests) call
       `git push -u origin <branch>` then
       `gh pr create --title "sdd-toolkit: promote <file> from <repo>" ...`.
       Never pushes the default branch (assert in code).
- `sdd sync --push [<file>...]` + `sdd sync --workspace <dir>` CLI:
  workspace iterates immediate children containing `.hornero/sdd.lock`
  and runs a pull-sync in each (skip everything else, report a summary).
- Tests `tests/test_sdd_push.py` with a `RecordingRunner` mock — **F4.5
  gate** assertions on the exact command payloads.

**NOT in scope**: real gh/network in tests, cross-repo insight rollups (OQ5).

## Codebase Contract (Anti-Hallucination)

```python
from hornero.sdd_toolkit.drift import DriftState, classify   # TASK-025
from hornero.sdd_toolkit.upstream import fetch_upstream      # TASK-021
# runner seam: Callable[[list[str], Path], CompletedProcess-like] — inject;
# tests must never spawn real gh (may not be installed/authenticated).
```

### Does NOT Exist
- ~~`gh` guaranteed on PATH~~ — prod runner reports a clear error when
  missing; tests always inject the mock

## Acceptance Criteria

- [ ] **F4.5 gate**: mock runner records branch creation + `gh pr create` with expected files/title; nothing targets the default branch
- [ ] Non-modified file in push list ⇒ refused, nothing pushed
- [ ] Secret-bearing file refused; `--allow-secrets` overrides for that run
- [ ] `--workspace` touches only lockfile-bearing children (assert siblings untouched)
- [ ] Full suite green; ruff + mypy clean

## Test Specification

```python
def test_f4_5_gate_push_branch_and_pr_payload(tmp_path): ...
def test_push_rejects_non_modified(tmp_path): ...
def test_secret_scan_refuses_and_override(tmp_path): ...
def test_workspace_fanout_only_lockfile_repos(tmp_path): ...
```

---

## Completion Note

**Completed by**: claude-fable-5
**Date**: 2026-07-08
**Notes**: hornero/sdd_toolkit/push.py — push() validates every named file is MODIFIED (offenders listed with their actual state, exit 1, zero side effects), runs the R9 secret scan (AWS keys, gh/ghp/github_pat tokens, sk- keys, Bearer, private-key blocks, URLs with userinfo; --allow-secrets overrides per run), then in the upstream checkout via the injected runner: checkout -B sdd-toolkit/promote-<repo>, copy, add, commit, push -u origin <branch>, gh pr create (title per §7). Branch namespace asserted in code — nothing can target main/master. Empty file list refused listing modified candidates (R8: per-file, explicit). subprocess_runner reports a missing gh binary as a clear error (127). cmd_workspace iterates immediate children with .hornero/sdd.lock, pull-syncs each against its own lock identity, skips the rest, propagates the worst rc. F4.5 GATE GREEN: RecordingRunner receives the exact branch + PR payloads; workspace touches only lockfile-bearing children (sibling bytes asserted untouched). Suite 189 passed, ruff + mypy clean. SPEC-002 scope closes with this task.

**Deviations from spec**: push signature adds source/ref (the upstream to promote into — needed by fetch_upstream; the CLI resolves them exactly like sync). Multi-file pushes title "promote N files from <repo>" (spec's title shape is per-file).

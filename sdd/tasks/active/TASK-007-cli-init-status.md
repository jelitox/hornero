# TASK-007: CLI skeleton — `hornero init` + `hornero status` + config loading (F1 gate closer)

**Feature**: SPEC-001 — Hornero: foundational contracts and MVP scope
**Spec**: `sdd/specs/SPEC-001-hornero-foundation.md`
**Status**: pending
**Priority**: high
**Estimated effort**: L (4-8h)
**Depends-on**: TASK-003, TASK-004, TASK-005
**Assigned-to**: unassigned

---

## Context

SPEC-001 §10 defines the CLI surface. This task delivers the two F1 commands
and the config plumbing, then **closes the F1 phase gate**: with this task
done, `pytest tests/test_lifecycle.py tests/test_inbox.py -q` must be green
AND `hornero init && hornero status` must exit 0 on an empty repo. Do not let
any F2 task start while this gate is red (CLAUDE.md phase-gate rule).

Phase: **F1 — Skeleton** (gate closer).

---

## Scope

- Implement `hornero/cli.py` with entry point `main()` (pyproject already
  declares `hornero = "hornero.cli:main"` — verified). Use **stdlib
  `argparse`** with subcommands; `click`/`typer`/`rich` are not installed and
  this task must not add dependencies.
- `hornero init` — scaffold in the current repo (idempotent, §4 layout):
  - `.hornero/inbox/`, `.hornero/processed/`, `.hornero/knowledge/`
    (with `.gitkeep` files so empty dirs survive git)
  - `.hornero/config.yaml` — default config (see below); do not overwrite an
    existing one
  - `product/specs/`, `product/decisions/`, `product/reports/`
  - append `.hornero/ledger.db` to the target repo's `.gitignore` if missing
  - initialize the ledger schema (TASK-004 `Ledger`)
- `hornero status` — print: spec counts by state (via TASK-003 `SpecCorpus`),
  pending inbox count (via TASK-005 `InboxSource.poll`), index health
  (MVP: "knowledge index: absent/present"; staleness detection is F4/TASK-016
  — print `unknown` until then). Exit 0 even when everything is empty.
- `hornero/config.py` — `load_config(root) -> HorneroConfig` dataclass:
  ports/adapter selection, backend order, criterion allowlist, models
  (§4 config.yaml comment). `yaml.safe_load`; missing file ⇒ defaults.
  Unknown keys ⇒ error (fail-closed, catches typos).
- Register stubs for `reconcile`, `build`, `reindex`, `report` that print
  "not implemented (phase F2/F3/F4/F5)" and **exit non-zero** — the CLI
  surface is complete but honest.
- Tests in `tests/test_cli.py` (run `main(argv)` in-process against
  `tmp_path`; also exercise idempotent re-init).

**NOT in scope**: reconcile/build/reindex/report implementations
(TASK-012/015/16/19), TTY/HITL concerns (TASK-010).

---

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `hornero/cli.py` | CREATE | argparse CLI: init, status + stubs |
| `hornero/config.py` | CREATE | config.yaml loader (fail-closed) |
| `tests/test_cli.py` | CREATE | init/status/idempotency tests |

---

## Codebase Contract (Anti-Hallucination)

> **CRITICAL**: verified against the repo on 2026-07-06. TASK-003/004/005
> must be completed first — verify their real signatures on pickup.

### Verified Imports
```python
import argparse                      # stdlib — the ONLY CLI framework available
import yaml                          # runtime dep added by TASK-003 (pyyaml)
from hornero.lifecycle import SpecCorpus       # TASK-003
from hornero.memory.ledger import Ledger       # TASK-004
from hornero.adapters.inbox import InboxSource # TASK-005
```

### Existing Signatures to Use
```python
# pyproject.toml (verified):
# [project.scripts]
# hornero = "hornero.cli:main"     ← main() must exist with this exact name
```

### Does NOT Exist
- ~~`click`, `typer`, `rich`~~ — NOT installed (verified); argparse only
- ~~`hornero.reconciler`~~ — F2 package, does not exist yet; stubs must not import it
- ~~`hornero.config` before this task~~ — you create it
- ~~staleness detection~~ — TASK-016; print `unknown`, do not fake it

---

## Implementation Notes

### Pattern to Follow
Default `config.yaml` written by `init` (comment-annotated):
```yaml
signal_source: inbox          # SignalSource adapter
tracker: repo                 # TrackerPort adapter
dispatch:
  backend_order: [mock]       # NEVER auto-includes api (CLAUDE.md invariant 3)
criterion_allowlist: [pytest, ruff, mypy, python]
models: {}
```

### Key Constraints
- `main(argv: list[str] | None = None) -> int` and module-level
  `sys.exit(main())` guard — testable in-process, no subprocess needed
  (subprocess smoke test optional).
- `init` twice ⇒ identical tree, exit 0 (idempotent).
- `status` must never require network/LLM/Redis (invariant 6) and never
  mutate anything.
- Config `backend_order` may list `api` only if the user wrote it — `init`
  defaults never include it (no billed backend by surprise).

### References in Codebase
- SPEC-001 §4 (layout to scaffold), §10 (CLI surface), F1 gate row in §12.
- `.gitignore` (verified) already ignores `.hornero/ledger.db` in THIS repo;
  `init` must ensure the same in TARGET repos.

---

## Acceptance Criteria

- [ ] `hornero init && hornero status` exits 0 on an empty repo (**F1 gate, run it literally** in a scratch dir)
- [ ] `pytest tests/test_lifecycle.py tests/test_inbox.py -q` green (**F1 gate**)
- [ ] Re-running `init` is a no-op; existing `config.yaml` never overwritten
- [ ] Unknown config key ⇒ non-zero exit with a clear message
- [ ] Stub subcommands exit non-zero with "not implemented"
- [ ] All tests pass: `pytest tests/test_cli.py -q`; `ruff check` + `mypy hornero` clean

---

## Test Specification

```python
# tests/test_cli.py
from hornero.cli import main


def test_init_scaffolds_layout(tmp_path, monkeypatch): ...
def test_init_idempotent(tmp_path, monkeypatch): ...
def test_init_preserves_existing_config(tmp_path, monkeypatch): ...
def test_status_exit_zero_on_fresh_repo(tmp_path, monkeypatch): ...
def test_unknown_config_key_fails_closed(tmp_path, monkeypatch): ...
def test_stub_commands_exit_nonzero(tmp_path, monkeypatch): ...
```

---

## Agent Instructions

When you pick up this task:

1. **Read the spec** at the path listed above for full context
2. **Check dependencies** — verify TASK-003, TASK-004, TASK-005 are in `sdd/tasks/completed/`
3. **Verify the Codebase Contract** — before writing ANY code
4. **Update status** in `sdd/tasks/index/hornero-foundation.json` → `"in-progress"`
5. **Implement** following the scope, codebase contract, and notes above
6. **Verify** all acceptance criteria are met — including running the F1 gate commands literally
7. **Move this file** to `sdd/tasks/completed/TASK-007-cli-init-status.md`
8. **Update index** → `"done"`
9. **Fill in the Completion Note** below

---

## Completion Note

*(Agent fills this in when done)*

**Completed by**:
**Date**:
**Notes**:

**Deviations from spec**: none

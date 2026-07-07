# TASK-012: `hornero reconcile [--dry-run]` — pipeline wiring + F2 gate closer

**Feature**: SPEC-001 — Hornero: foundational contracts and MVP scope
**Spec**: `sdd/specs/SPEC-001-hornero-foundation.md`
**Status**: done
**Priority**: high
**Estimated effort**: M (2-4h)
**Depends-on**: TASK-007, TASK-009, TASK-010, TASK-011
**Assigned-to**: unassigned

---

## Context

Wires §9's full pipeline behind `hornero reconcile` (§10):
poll → retrieve+draft → HITL → apply, with ledger records per run. This task
**closes the F2 phase gate**: a fixture inbox of 3 notes yields the expected
delta set with `FakeLLM`, every delta evidence-verified, and `--dry-run`
leaves the git diff empty.

Phase: **F2 — Reconciler** (gate closer).

---

## Scope

- Replace the `reconcile` stub in `hornero/cli.py` (TASK-007) with the real
  command in `hornero/reconciler/run.py` (keep `cli.py` thin):
  - Resolve adapters + knowledge layer from config; open the ledger; create
    a `run_id` (`r-<n>` monotonic from the ledger, deterministic).
  - Per polled signal: read text, `draft_deltas(...)` (TASK-009), collect.
  - `--dry-run`: print deltas (kind, title, confidence, evidence excerpts)
    and **stop — no HITL gate, no apply, no ack, no spec mutation; ledger
    run row is written with `dry_run=1`** (operational state is gitignored,
    so git stays clean).
  - Normal run: `TerminalChannel.open()` — `None` (no TTY) ⇒ fail-closed:
    report "no approval channel; N deltas remain proposed", exit 0, apply
    nothing (invariant 2). Otherwise `gate(...)` (TASK-010) then
    `apply_deltas(...)` (TASK-011); record deltas + outcomes in the ledger.
  - LLM resolution: config `models:` is empty in MVP — the CLI accepts an
    injected `LLMPort` factory for tests; without a configured model the
    command exits non-zero with "no model configured" BEFORE polling
    (fail-closed, no half-run).
- **F2 gate fixtures**: `tests/fixtures/inbox_notes/` with 3 meeting-note
  files + a scripted `FakeLLM` producing a known delta set (mix: one NEW,
  one CHANGED, one with a fabricated excerpt that must be dropped, one
  DUPLICATE).
- e2e test `tests/test_reconcile_e2e.py` (in-process `main()` calls):
  - dry-run on the fixture repo → expected delta set printed, `git status
    --porcelain` empty afterwards (init a scratch git repo in the test).
  - scripted-channel run → approved delta applied, signal acked, ledger rows
    present.
  - no-TTY run → nothing mutated.

**NOT in scope**: build/dispatch (F3), reindex (F4), arena votes (post-MVP).

---

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `hornero/reconciler/run.py` | CREATE | pipeline orchestration |
| `hornero/cli.py` | MODIFY | wire real `reconcile`, add `--dry-run` flag |
| `tests/fixtures/inbox_notes/` | CREATE | 3 fixture notes (deterministic content) |
| `tests/test_reconcile_e2e.py` | CREATE | F2 gate test |

---

## Codebase Contract (Anti-Hallucination)

> **CRITICAL**: verified against the repo on 2026-07-06. Every import below
> is produced by a dependency task — re-verify real names on pickup.

### Verified Imports
```python
from hornero.config import load_config              # TASK-007
from hornero.memory.ledger import Ledger            # TASK-004
from hornero.memory.knowledge import open_knowledge # TASK-008
from hornero.reconciler.draft import draft_deltas   # TASK-009
from hornero.reconciler.hitl import TerminalChannel, gate   # TASK-010
from hornero.reconciler.apply import apply_deltas   # TASK-011
from hornero.reconciler.testing import FakeLLM      # TASK-009
```

### Existing Signatures to Use
```python
# hornero/cli.py (TASK-007): main(argv) -> int; subcommand registry pattern —
# read the actual file before modifying; replace ONLY the reconcile stub.
```

### Does NOT Exist
- ~~a real LLM client / API key path~~ — tests inject FakeLLM; the command
  without a model config exits non-zero, it does NOT fall back to anything
- ~~`--yes` / auto-approve flags~~ — forbidden (G3)
- ~~network, Redis, Jira~~ — nothing in this task may touch them (invariant 6)

---

## Implementation Notes

### Key Constraints
- **The F2 gate is the acceptance test** — encode it literally: 3 fixture
  notes, expected delta set asserted field-by-field (kind, title,
  affected_specs, evidence excerpts), the fabricated-excerpt draft asserted
  ABSENT + present in `dropped_drafts` with `evidence_mismatch`.
- `--dry-run` cleanliness is asserted via `git status --porcelain` in a
  scratch repo — mirrors the gate wording exactly ("git diff empty").
- Deterministic run ids; no timestamps in printed output that tests assert on
  (or inject the clock).
- Keep `cli.py` argparse-only; presentation is plain text.

### References in Codebase
- SPEC-001 §9 (pipeline), §10 (CLI + dry-run semantics), §12 F2 gate row;
  CLAUDE.md invariant 2 + phase-gate rules.

---

## Acceptance Criteria

- [ ] **F2 gate**: fixture inbox (3 notes) + FakeLLM → expected delta set; every surviving delta evidence-verified; fabricated draft dropped + ledger-logged
- [ ] **F2 gate**: `hornero reconcile --dry-run` leaves `git status --porcelain` empty
- [ ] No-TTY normal run: zero mutations, exit 0, clear message
- [ ] Approved-path e2e: spec created/patched, signal acked, ledger complete
- [ ] All tests pass: `pytest tests/test_reconcile_e2e.py -q` and full suite `pytest -q`
- [ ] `ruff check` + `mypy hornero` clean

---

## Test Specification

```python
# tests/test_reconcile_e2e.py
from hornero.cli import main


def test_f2_gate_dry_run_expected_deltas_and_clean_git(tmp_path): ...
def test_f2_gate_evidence_mismatch_dropped(tmp_path): ...
def test_no_tty_fail_closed(tmp_path, monkeypatch): ...
def test_approved_delta_applied_and_acked(tmp_path): ...
def test_no_model_configured_exits_nonzero_before_polling(tmp_path): ...
```

---

## Agent Instructions

When you pick up this task:

1. **Read the spec** at the path listed above for full context
2. **Check dependencies** — verify TASK-007, TASK-009, TASK-010, TASK-011 are in `sdd/tasks/completed/`
3. **Verify the Codebase Contract** — before writing ANY code
4. **Update status** in `sdd/tasks/index/hornero-foundation.json` → `"in-progress"`
5. **Implement** following the scope, codebase contract, and notes above
6. **Verify** all acceptance criteria are met — the F2 gate must be green before any F3 task starts
7. **Move this file** to `sdd/tasks/completed/TASK-012-reconcile-cli-e2e.md`
8. **Update index** → `"done"`
9. **Fill in the Completion Note** below

---

## Completion Note

**Completed by**: claude-fable-5 (session 0d52d2f9)
**Date**: 2026-07-06
**Notes**: hornero/reconciler/run.py wires poll->draft->HITL->apply with ledger records; cli reconcile real. F2 GATE GREEN: 3 fixture notes + FakeLLM => expected set (1 new, 1 changed, 1 duplicate), fabricated draft dropped+logged evidence_mismatch, --dry-run leaves git status --porcelain empty, no-TTY run fail-closed, approved path creates SPEC-002 + patches SPEC-001 + acks 2 signals. Also fixed gitignore pattern to ledger.db* (SQLite WAL siblings would dirty the tree). Full suite 96 passed.

**Deviations from spec**: model resolution MVP: only fake:<script.json> is supported; unset/unsupported models refuse before polling (exit 3). Real providers arrive behind the same LLMPort seam post-MVP; delta ids namespaced per signal (dlt-<run>.<i>-<n>) to keep them unique across signals.

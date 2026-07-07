# TASK-010: HITL gate — fail-closed terminal approval

**Feature**: SPEC-001 — Hornero: foundational contracts and MVP scope
**Spec**: `sdd/specs/SPEC-001-hornero-foundation.md`
**Status**: done
**Priority**: high
**Estimated effort**: M (2-4h)
**Depends-on**: TASK-002
**Assigned-to**: unassigned

---

## Context

SPEC-001 §9 step 4 and G3: every delta passes a human gate before anything is
created or dispatched. **Fail-closed**: no TTY, no approval channel ⇒ no
approvals, no exception — everything stays `proposed` (CLAUDE.md invariant 2:
"No approval channel => no spec mutation, no dispatch, no exception").

Phase: **F2 — Reconciler**.

---

## Scope

- Implement `hornero/reconciler/hitl.py`:
  - `ApprovalChannel(Protocol)`: `review(delta: RequirementDelta, diff_text: str) -> Decision`
    where `Decision(StrEnum)` = `APPROVED | REJECTED | EDITED | SKIPPED`,
    plus `EDITED` carries the edited patch — model the return as a small
    `ReviewResult` dataclass (`decision`, `patch: str | None`).
  - `TerminalChannel` — interactive TTY implementation:
    - Renders the delta: kind, title, summary, confidence (displayed, never
      used to auto-approve — §13 R1), evidence excerpts with locators, and a
      unified diff view of `proposed_patch` (stdlib `difflib` for CHANGED;
      full-body preview for NEW).
    - Prompts `[a]pprove / [r]eject / [e]dit / [s]kip` per delta.
    - `e` opens `$EDITOR` on the patch in a tempfile (OQ1's leaning —
      implement `$EDITOR`; if `$EDITOR` unset, fall back to reject with a
      message, never approve).
    - **Constructor/factory refuses a non-TTY**: `TerminalChannel.open()`
      returns `None` when `not sys.stdin.isatty() or not sys.stdout.isatty()`.
  - `gate(deltas, channel: ApprovalChannel | None) -> list[ReviewedDelta]`:
    - `channel is None` ⇒ every delta result is `SKIPPED` (stays `proposed`),
      returns normally — **no exception** (fail-closed is a quiet outcome).
    - `DUPLICATE` deltas are never presented (§6: "not presented for
      approval"); they pass through marked `SKIPPED` with a note.
- Tests in `tests/test_hitl.py` — non-interactive by construction: a
  `ScriptedChannel` test double drives decisions; TTY-refusal tested by
  monkeypatching `isatty`.

**NOT in scope**: applying approved deltas (TASK-011), ledger writes
(TASK-012 orchestrates), rich/curses UI (NG4 — plain terminal only).

---

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `hornero/reconciler/hitl.py` | CREATE | ApprovalChannel, TerminalChannel, gate |
| `tests/test_hitl.py` | CREATE | fail-closed + decision-flow tests |

---

## Codebase Contract (Anti-Hallucination)

> **CRITICAL**: verified against the repo on 2026-07-06.

### Verified Imports
```python
import difflib, os, sys, subprocess, tempfile      # stdlib
from enum import StrEnum
from hornero.models import DeltaKind, RequirementDelta   # TASK-002
```

### Existing Signatures to Use
```python
# hornero/models.py (TASK-002):
class RequirementDelta:
    kind: DeltaKind          # NEW|CHANGED|OBSOLETE|DUPLICATE
    proposed_patch: str      # full body (NEW) or unified diff (CHANGED)
    confidence: float        # DISPLAY only — never a threshold
    status: str              # "proposed"|"approved"|"rejected"
```

### Does NOT Exist
- ~~`rich`, `prompt_toolkit`, `questionary`, `click`~~ — NOT installed
  (verified); stdlib `input()` + `difflib` + ANSI-free output
- ~~auto-approve thresholds / `--yes` flag~~ — forbidden by G3; do not add
- ~~`hornero.reconciler.hitl` before this task~~ — you create it
- ~~Oddie's `ConfirmationGuard`~~ — referenced in the spec as a *philosophy*
  ("human_manager=None ⇒ deny"), not an importable dependency

---

## Implementation Notes

### Key Constraints
- Fail-closed must be **boring**: `gate(deltas, None)` returns all-SKIPPED,
  exit path identical to "human skipped everything". No stack trace, no
  warning storm — one clear log line.
- Editing: after `$EDITOR` returns, re-validate the patch is non-empty; the
  edited delta keeps its evidence (evidence is about the SIGNAL, the patch is
  the proposal — editing the patch does not touch evidence).
- Never mutate `delta.status` for SKIPPED; TASK-011/012 owns persistence of
  approved/rejected outcomes.
- No timeouts, no default answers on empty input (re-prompt).

### References in Codebase
- SPEC-001 §9 step 4, §6 DUPLICATE rule, §14 OQ1 ($EDITOR leaning),
  CLAUDE.md invariant 2.

---

## Acceptance Criteria

- [ ] `gate(deltas, None)` → all SKIPPED, no exception, nothing mutated
- [ ] `TerminalChannel.open()` returns `None` when stdin or stdout is not a TTY
- [ ] DUPLICATE deltas never reach the channel (ScriptedChannel records calls)
- [ ] approve/reject/edit/skip each produce the right `ReviewResult`
- [ ] `$EDITOR` unset + edit chosen ⇒ falls back to reject, never approve
- [ ] All tests pass: `pytest tests/test_hitl.py -q`; `ruff check` + `mypy hornero` clean

---

## Test Specification

```python
# tests/test_hitl.py
from hornero.reconciler.hitl import Decision, TerminalChannel, gate


def test_no_channel_means_all_skipped(): ...
def test_non_tty_refuses_to_open(monkeypatch): ...
def test_duplicate_never_presented(): ...
def test_scripted_approve_reject_edit_skip(): ...
def test_edit_without_editor_falls_back_to_reject(monkeypatch): ...
```

---

## Agent Instructions

When you pick up this task:

1. **Read the spec** at the path listed above for full context
2. **Check dependencies** — verify TASK-002 is in `sdd/tasks/completed/`
3. **Verify the Codebase Contract** — before writing ANY code
4. **Update status** in `sdd/tasks/index/hornero-foundation.json` → `"in-progress"`
5. **Implement** following the scope, codebase contract, and notes above
6. **Verify** all acceptance criteria are met
7. **Move this file** to `sdd/tasks/completed/TASK-010-hitl-gate.md`
8. **Update index** → `"done"`
9. **Fill in the Completion Note** below

---

## Completion Note

**Completed by**: claude-fable-5 (session 0d52d2f9)
**Date**: 2026-07-06
**Notes**: hornero/reconciler/hitl.py: Decision/ReviewResult/ReviewedDelta, ApprovalChannel protocol, TerminalChannel.open() returning None off-TTY, $EDITOR edit flow falling back to reject, gate() skipping DUPLICATEs and returning all-SKIPPED quietly when channel is None. 7 non-interactive tests green.

**Deviations from spec**: none

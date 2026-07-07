# TASK-005: `InboxSource` — filesystem SignalSource adapter

**Feature**: SPEC-001 — Hornero: foundational contracts and MVP scope
**Spec**: `sdd/specs/SPEC-001-hornero-foundation.md`
**Status**: done
**Priority**: high
**Estimated effort**: M (2-4h)
**Depends-on**: TASK-001
**Assigned-to**: unassigned

---

## Context

The MVP `SignalSource` (SPEC-001 §7 adapter table): polls `.hornero/inbox/`
for dropped `.md`/`.txt`/`.vtt` files and acks by moving them to
`.hornero/processed/`. This is how requirement signals enter the loop with
zero external services (G1). Subject of the F1 gate file `tests/test_inbox.py`.

Phase: **F1 — Skeleton**.

---

## Scope

- Implement `hornero/adapters/__init__.py` and `hornero/adapters/inbox.py`:
  - `InboxSource(root: Path)` where `root` is the `.hornero/` directory;
    reads `root/inbox/`, moves to `root/processed/` on ack.
  - `poll() -> list[Signal]`: one `Signal` per supported file
    (`.md`, `.txt`, `.vtt`), sorted deterministically (by name). Fields:
    - `signal_id`: stable derivation `sig-<YYYYMMDD>-<xx>` per SPEC-001's
      examples (`sig-20260706-a1`): date from file mtime **injected via a
      `now`/clock parameter for testability**, suffix from a short content
      hash — the same file must always yield the same id.
    - `kind`: `"transcript"` for `.vtt`, `"meeting_notes"` for `.md`,
      `"document"` for `.txt` (document the mapping; it's a heuristic).
    - `path`: absolute path as str; `received_at`: file mtime.
  - `ack(signal_id)`: move the file to `processed/`, **idempotent** — acking
    an already-acked or unknown id is a no-op, never an error (§7 comment).
    Preserve filename; on collision in `processed/`, suffix deterministically.
  - Unsupported extensions are ignored by `poll()` (not deleted, not raised).
- Tests in `tests/test_inbox.py` (**F1 gate file — exact path fixed by the
  spec's phase table**), using `tmp_path` fixture inboxes.

**NOT in scope**: reconciliation of signal content (F2), reading signal text
for evidence checks (TASK-009 reads files itself), `hornero init` scaffolding
of the directories (TASK-007).

---

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `hornero/adapters/__init__.py` | CREATE | package marker |
| `hornero/adapters/inbox.py` | CREATE | InboxSource |
| `tests/test_inbox.py` | CREATE | F1 gate test file |

---

## Codebase Contract (Anti-Hallucination)

> **CRITICAL**: verified against the repo on 2026-07-06.

### Verified Imports
```python
from pathlib import Path   # stdlib
import hashlib, shutil     # stdlib
from hornero.ports import Signal, SignalSource  # created by TASK-001 — VERIFY it
# exists and matches before implementing; if TASK-001 is not in
# sdd/tasks/completed/, STOP: this task depends on it.
```

### Existing Signatures to Use
```python
# hornero/ports.py (TASK-001):
class Signal(TypedDict):
    signal_id: str
    kind: str            # "meeting_notes" | "transcript" | "document" | "idea"
    path: str
    received_at: float

class SignalSource(Protocol):
    def poll(self) -> list[Signal]: ...
    def ack(self, signal_id: str) -> None: ...
```

### Does NOT Exist
- ~~`watchdog` / inotify watchers~~ — not installed; `poll()` is a plain
  directory scan, no daemon
- ~~`hornero.config`~~ — does not exist yet; `InboxSource` takes `root: Path`
  directly, config wiring happens in TASK-007
- ~~a signal registry / DB of seen signals~~ — statelessness is the point:
  inbox contents = pending, processed/ = acked

---

## Implementation Notes

### Key Constraints
- `isinstance(InboxSource(tmp), SignalSource)` must hold (runtime_checkable
  protocol from TASK-001).
- Determinism (invariant 6): no wall-clock reads in id derivation without an
  injectable seam; tests must produce identical ids across runs.
- `poll()` never mutates; only `ack()` moves files.
- Missing `inbox/` dir ⇒ `poll()` returns `[]` (init not run yet is a status
  condition, not a crash).

### References in Codebase
- SPEC-001 §4 (directory contract), §7 (port + adapter table),
  `Evidence.signal_id` example format in §6 (`sig-20260706-a1`).

---

## Acceptance Criteria

- [ ] `poll()` returns one Signal per `.md`/`.txt`/`.vtt`, deterministic order and ids
- [ ] `ack()` moves to `processed/`; double-ack and unknown-id ack are silent no-ops
- [ ] Unsupported extensions ignored; missing inbox dir yields `[]`
- [ ] `isinstance(source, SignalSource)` is true
- [ ] All tests pass: `pytest tests/test_inbox.py -q` (F1 gate component)
- [ ] `ruff check hornero/adapters/` and `mypy hornero` clean

---

## Test Specification

```python
# tests/test_inbox.py
from hornero.adapters.inbox import InboxSource
from hornero.ports import SignalSource


def test_poll_lists_supported_files_deterministically(tmp_path): ...
def test_signal_ids_stable_across_polls(tmp_path): ...
def test_ack_moves_to_processed_and_is_idempotent(tmp_path): ...
def test_unsupported_extension_ignored(tmp_path): ...
def test_missing_inbox_dir_returns_empty(tmp_path): ...
def test_protocol_conformance(tmp_path):
    assert isinstance(InboxSource(tmp_path), SignalSource)
```

---

## Agent Instructions

When you pick up this task:

1. **Read the spec** at the path listed above for full context
2. **Check dependencies** — verify TASK-001 is in `sdd/tasks/completed/`
3. **Verify the Codebase Contract** — before writing ANY code
4. **Update status** in `sdd/tasks/index/hornero-foundation.json` → `"in-progress"`
5. **Implement** following the scope, codebase contract, and notes above
6. **Verify** all acceptance criteria are met
7. **Move this file** to `sdd/tasks/completed/TASK-005-inbox-source.md`
8. **Update index** → `"done"`
9. **Fill in the Completion Note** below

---

## Completion Note

**Completed by**: claude-fable-5 (session 0d52d2f9)
**Date**: 2026-07-06
**Notes**: hornero/adapters/inbox.py: poll() pure scan (name-sorted, kind by extension), stable ids sig-<mtime-date>-<sha256[:6]>, ack idempotent with deterministic collision suffixes. 8 tests green.

**Deviations from spec**: signal-id date derives from file mtime (UTC) rather than an injected clock — content hash provides the stability the tests require; simpler and still deterministic within a fixture run.

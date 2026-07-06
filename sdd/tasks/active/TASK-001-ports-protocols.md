# TASK-001: Ports — `Signal`, `SignalSource`, `TrackerPort`, `DispatchPort` protocols

**Feature**: SPEC-001 — Hornero: foundational contracts and MVP scope
**Spec**: `sdd/specs/SPEC-001-hornero-foundation.md`
**Status**: pending
**Priority**: high
**Estimated effort**: S (< 2h)
**Depends-on**: none
**Assigned-to**: unassigned

---

## Context

SPEC-001 §7 defines three stable ports (G2) so any environment can plug its
own adapters without touching core. This task creates the typing module that
every adapter task (TASK-005, TASK-006, TASK-014) implements against. Core
never imports an adapter.

Phase: **F1 — Skeleton**.

---

## Scope

- Implement `hornero/ports.py` containing, verbatim per SPEC-001 §7:
  - `Signal(TypedDict)`: `signal_id: str`, `kind: str`, `path: str`,
    `received_at: float`.
  - `SignalSource(Protocol)`: `poll() -> list[Signal]`,
    `ack(signal_id: str) -> None` (ack is idempotent — document it).
  - `TrackerPort(Protocol)`: `upsert(spec_path: str) -> str`,
    `transition(ref: str, status: str) -> None`,
    `comment(ref: str, body: str) -> None`.
  - `BuildBrief(TypedDict)`: `spec_id`, `kind`, `summary`, `description`,
    `acceptance_criteria: list[str]`, `repo_path`.
  - `BuildResult(TypedDict)`: `status: str` (`completed|failed|needs_human`),
    `pr_url: str | None`, `branch: str | None`, `log_path: str`.
  - `DispatchPort(Protocol)`: `dispatch(brief: BuildBrief) -> BuildResult`.
- Protocols must be `@runtime_checkable` so adapters can be verified with
  `isinstance` in tests and in the config resolver (TASK-007).
- Write structural tests in `tests/test_ports.py`.

**NOT in scope**: any adapter implementation (TASK-005/006/014), config
resolution (TASK-007), the `RequirementDelta` model (TASK-002).

---

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `hornero/ports.py` | CREATE | The three Protocols + TypedDicts |
| `tests/test_ports.py` | CREATE | Structural conformance tests |

---

## Codebase Contract (Anti-Hallucination)

> **CRITICAL**: verified against the repo on 2026-07-06. Do not invent
> imports. If you need something not listed, verify it exists first.

### Verified Imports
```python
from typing import Protocol, TypedDict, runtime_checkable  # stdlib, py>=3.11
```

### Existing Signatures to Use
```python
# pyproject.toml (verified): requires-python = ">=3.11"; dependencies = []
# hornero/__init__.py (verified): exists and is EMPTY — the package has no
# other modules yet. This task creates the first real module.
```

### Does NOT Exist
- ~~`hornero.ports`~~ — this task creates it; nothing imports it yet
- ~~`parrot`, `multicoders`~~ — NOT installed in `.venv` (verified); do not import
- ~~`pydantic`, `attrs`~~ — not installed; use stdlib `typing` only
- ~~any `hornero.adapters` package~~ — created later by TASK-005/006

---

## Implementation Notes

### Key Constraints
- Pure typing module: zero runtime dependencies, zero I/O, no third-party
  imports. `python -c "import hornero.ports"` must work in a bare venv.
- Copy field names/types **exactly** from SPEC-001 §7 — these are the public
  contract (G2); downstream tasks quote them verbatim.
- Docstrings must capture the behavioral contracts the type system cannot:
  `ack` idempotent; `dispatch` never raises for `failed` (it returns
  `status="failed"`); `TrackerPort.upsert` returns an external ref string.

### References in Codebase
- SPEC-001 §7 — the literal source of every signature.

---

## Acceptance Criteria

- [ ] `from hornero.ports import Signal, SignalSource, TrackerPort, DispatchPort, BuildBrief, BuildResult` works
- [ ] All three Protocols are `runtime_checkable`
- [ ] A minimal in-test fake satisfies `isinstance(fake, SignalSource)` (same for the other two ports)
- [ ] All tests pass: `pytest tests/test_ports.py -q`
- [ ] `ruff check hornero/ports.py` and `mypy hornero` clean

---

## Test Specification

```python
# tests/test_ports.py
from hornero.ports import DispatchPort, SignalSource, TrackerPort


class _FakeSource:
    def poll(self): return []
    def ack(self, signal_id: str) -> None: ...


def test_signal_source_is_runtime_checkable():
    assert isinstance(_FakeSource(), SignalSource)


def test_non_conforming_object_rejected():
    assert not isinstance(object(), SignalSource)
    assert not isinstance(object(), TrackerPort)
    assert not isinstance(object(), DispatchPort)
```

---

## Agent Instructions

When you pick up this task:

1. **Read the spec** at the path listed above for full context
2. **Check dependencies** — none for this task
3. **Verify the Codebase Contract** — before writing ANY code
4. **Update status** in `sdd/tasks/index/hornero-foundation.json` → `"in-progress"`
5. **Implement** following the scope, codebase contract, and notes above
6. **Verify** all acceptance criteria are met
7. **Move this file** to `sdd/tasks/completed/TASK-001-ports-protocols.md`
8. **Update index** → `"done"`
9. **Fill in the Completion Note** below

---

## Completion Note

*(Agent fills this in when done)*

**Completed by**:
**Date**:
**Notes**:

**Deviations from spec**: none

# TASK-002: `RequirementDelta` model with mechanical evidence verification

**Feature**: SPEC-001 — Hornero: foundational contracts and MVP scope
**Spec**: `sdd/specs/SPEC-001-hornero-foundation.md`
**Status**: done
**Priority**: high
**Estimated effort**: M (2-4h)
**Depends-on**: none
**Assigned-to**: unassigned

---

## Context

SPEC-001 §6 defines the core model of the whole product: a typed requirement
delta whose grounding is **verbatim evidence, verified mechanically** (hard
invariant 1 in `CLAUDE.md`: "Evidence is verbatim or the delta dies"). This
module is imported by the reconciler (TASK-009), HITL gate (TASK-010), and
apply step (TASK-011).

Phase: **F1 — Skeleton** (model only; the LLM drafting pipeline is F2).

---

## Scope

- Implement `hornero/models.py` containing, verbatim per SPEC-001 §6:
  - `DeltaKind(StrEnum)`: `NEW`, `CHANGED`, `OBSOLETE`, `DUPLICATE`.
  - `@dataclass(frozen=True) Evidence`: `signal_id: str`, `excerpt: str`
    (<= 500 chars), `locator: str`.
  - `@dataclass RequirementDelta`: `delta_id`, `kind`, `title`, `summary`,
    `affected_specs: list[str]`, `evidence: list[Evidence]`,
    `confidence: float`, `proposed_patch: str`, `status: str = "proposed"`,
    `verdicts: list[dict] = field(default_factory=list)`.
- Enforce the hard invariants **in code, raising on violation — never
  silently fixed** (SPEC-001 §6):
  - `evidence` non-empty (raise `ValueError` in `__post_init__`).
  - `kind == NEW` ⇔ `affected_specs == []` (both directions).
  - `Evidence.excerpt` length <= 500 and non-empty; `confidence` in [0.0, 1.0].
- Implement the mechanical verbatim check as a standalone function:
  `verify_evidence(delta: RequirementDelta, signal_text_by_id: Mapping[str, str]) -> list[Evidence]`
  returning the evidence items whose `excerpt` is **not** an exact substring
  (`excerpt in signal_text`) of the referenced signal's text. Empty list ⇒
  fully grounded. No fuzzy matching, no normalization beyond nothing — the
  check is a literal `in`. (The caller — TASK-009 — drops deltas with
  mismatches and ledger-logs `evidence_mismatch`; this function only detects.)
- Tests in `tests/test_models.py`.

**NOT in scope**: LLM drafting, ledger logging of dropped deltas (TASK-009),
spec-file mutation (TASK-011), arena verdicts (post-MVP).

---

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `hornero/models.py` | CREATE | DeltaKind, Evidence, RequirementDelta, verify_evidence |
| `tests/test_models.py` | CREATE | Invariant + verbatim-check tests |

---

## Codebase Contract (Anti-Hallucination)

> **CRITICAL**: verified against the repo on 2026-07-06.

### Verified Imports
```python
from dataclasses import dataclass, field   # stdlib
from enum import StrEnum                   # stdlib, requires py>=3.11 (pyproject pins >=3.11)
from typing import Mapping                 # stdlib
```

### Existing Signatures to Use
```python
# SPEC-001 §6 is the literal source — copy field names, types, defaults verbatim.
# hornero/__init__.py (verified): empty; hornero/models.py does not exist yet.
```

### Does NOT Exist
- ~~`pydantic`~~ — not installed; use stdlib dataclasses exactly as the spec shows
- ~~`hornero.reconciler`~~ — package does not exist yet (F2, TASK-009+)
- ~~`hornero.memory.ledger`~~ — does not exist yet (TASK-004); do NOT log from this module
- ~~any fuzzy/normalized matching helper~~ — the spec mandates a literal substring check

---

## Implementation Notes

### Pattern to Follow
```python
@dataclass(frozen=True)
class Evidence:
    signal_id: str
    excerpt: str
    locator: str

    def __post_init__(self) -> None:
        if not self.excerpt or len(self.excerpt) > 500:
            raise ValueError(...)
```

### Key Constraints
- Invariant violations raise `ValueError` with a message naming the field —
  they are bugs upstream, never "acceptable for now" (CLAUDE.md).
- `verify_evidence` is pure (no I/O, no logging); determinism is what makes
  invariant 1 testable.
- `DUPLICATE` semantics (persisted, never dispatched) are enforced by
  consumers, not here — but document them in the `DeltaKind` docstring.

### References in Codebase
- SPEC-001 §6 — the model, copied verbatim.
- SPEC-001 §9 step 2 — how `verify_evidence` will be consumed.

---

## Acceptance Criteria

- [ ] Model matches SPEC-001 §6 field-for-field
- [ ] `RequirementDelta(evidence=[])` raises `ValueError`
- [ ] `kind=NEW` with non-empty `affected_specs` raises; `kind=CHANGED` with empty `affected_specs` raises
- [ ] `verify_evidence` flags an excerpt differing by a single character; passes an exact substring
- [ ] All tests pass: `pytest tests/test_models.py -q`
- [ ] `ruff check hornero/models.py` and `mypy hornero` clean

---

## Test Specification

```python
# tests/test_models.py
import pytest
from hornero.models import DeltaKind, Evidence, RequirementDelta, verify_evidence


def _delta(**kw):
    base = dict(
        delta_id="dlt-r1-1", kind=DeltaKind.NEW, title="t", summary="s",
        affected_specs=[], evidence=[Evidence("sig-a", "export as CSV", "L4")],
        confidence=0.9, proposed_patch="...",
    )
    base.update(kw)
    return RequirementDelta(**base)


def test_evidence_required():
    with pytest.raises(ValueError):
        _delta(evidence=[])


def test_new_iff_no_affected_specs():
    with pytest.raises(ValueError):
        _delta(kind=DeltaKind.NEW, affected_specs=["SPEC-002"])
    with pytest.raises(ValueError):
        _delta(kind=DeltaKind.CHANGED, affected_specs=[])


def test_verbatim_substring_check():
    d = _delta()
    assert verify_evidence(d, {"sig-a": "we should export as CSV monthly"}) == []
    mismatches = verify_evidence(d, {"sig-a": "we should export as PDF monthly"})
    assert mismatches == d.evidence
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
7. **Move this file** to `sdd/tasks/completed/TASK-002-requirement-delta-model.md`
8. **Update index** → `"done"`
9. **Fill in the Completion Note** below

---

## Completion Note

**Completed by**: claude-fable-5 (session 0d52d2f9)
**Date**: 2026-07-06
**Notes**: hornero/models.py per SPEC-001 §6: DeltaKind, Evidence (frozen, bounds-checked), RequirementDelta (invariants raise in __post_init__), verify_evidence as pure literal-substring detector. 9 tests; ruff + mypy clean.

**Deviations from spec**: none

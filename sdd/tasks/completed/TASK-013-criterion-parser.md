# TASK-013: Acceptance-criterion parser — `ShellCriterion` / `ManualCriterion`

**Feature**: SPEC-001 — Hornero: foundational contracts and MVP scope
**Spec**: `sdd/specs/SPEC-001-hornero-foundation.md`
**Status**: done
**Priority**: medium
**Estimated effort**: S (< 2h)
**Depends-on**: none
**Assigned-to**: unassigned

---

## Context

SPEC-001 §5: spec `acceptance_criteria` strings intentionally mirror the
dev_loop parser — allowlisted shell heads become `ShellCriterion`, everything
else (or an explicit `manual:` prefix) becomes `ManualCriterion` — so specs
translate 1:1 into `BuildBrief`s (R2: the criteria the spec declares ARE the
QA gate).

Phase: **F3 — Dispatch bridge** (pure string parsing; no dependencies, may
start any time, but F3 does not close before F2's gate is green).

---

## Scope

- Implement `hornero/criteria.py`:
  - `@dataclass(frozen=True) ShellCriterion`: `command: str`, `head: str`.
  - `@dataclass(frozen=True) ManualCriterion`: `description: str`.
  - `Criterion = ShellCriterion | ManualCriterion`.
  - `parse_criterion(raw: str, allowlist: Sequence[str]) -> Criterion`:
    - `manual:` prefix (case-insensitive, strip) ⇒ `ManualCriterion`.
    - First shell token (`shlex.split`) in `allowlist` ⇒ `ShellCriterion`.
    - Anything else ⇒ `ManualCriterion` (conservative: never executable by
      accident — an unallowlisted command degrades to manual, it does not
      raise and does not run).
    - Empty/whitespace raw ⇒ `ValueError`.
  - `parse_criteria(raws, allowlist) -> list[Criterion]` convenience.
- The allowlist comes from config (`criterion_allowlist`, TASK-007 default:
  `[pytest, ruff, mypy, python]`) — this module takes it as a parameter and
  has no config import.
- Tests in `tests/test_criteria.py`.

**NOT in scope**: executing criteria (the dispatched agent / dev-loop QA does
that, not hornero MVP), brief construction (TASK-014), config loading.

---

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `hornero/criteria.py` | CREATE | criterion types + parser |
| `tests/test_criteria.py` | CREATE | classification tests |

---

## Codebase Contract (Anti-Hallucination)

> **CRITICAL**: verified against the repo on 2026-07-06.

### Verified Imports
```python
import shlex                        # stdlib
from dataclasses import dataclass
from typing import Sequence
```

### Existing Signatures to Use
```python
# Example criteria, verbatim from SPEC-001 §5 frontmatter contract:
#   "pytest tests/export/test_csv.py -q"          -> ShellCriterion (head allowlisted)
#   "manual: CSV opens correctly in LibreOffice"  -> ManualCriterion
```

### Does NOT Exist
- ~~a dev_loop parser to import~~ — the spec says *mirror* its behavior;
  there is no `parrot`/dev_loop package in this venv (verified); implement
  standalone
- ~~criterion execution/subprocess code~~ — parsing only; nothing in this
  module runs commands
- ~~`hornero.config` import here~~ — allowlist is a parameter

---

## Implementation Notes

### Key Constraints
- Conservative default: unknown heads become MANUAL, never shell. The
  allowlist gates *executability classification*, which downstream QA relies
  on — misclassifying manual→shell is a security bug.
- `shlex.split` failures (unbalanced quotes) ⇒ `ManualCriterion` (again
  conservative), not an exception.
- Frozen dataclasses; module is pure and deterministic.

### References in Codebase
- SPEC-001 §5 (criterion syntax), §7 `BuildBrief.acceptance_criteria`,
  §13 R2.

---

## Acceptance Criteria

- [ ] Allowlisted head ⇒ `ShellCriterion` with correct `head`
- [ ] `manual:` prefix ⇒ `ManualCriterion` (prefix stripped)
- [ ] Unallowlisted head ⇒ `ManualCriterion`; unbalanced quotes ⇒ `ManualCriterion`
- [ ] Empty string ⇒ `ValueError`
- [ ] All tests pass: `pytest tests/test_criteria.py -q`; `ruff check` + `mypy hornero` clean

---

## Test Specification

```python
# tests/test_criteria.py
import pytest
from hornero.criteria import ManualCriterion, ShellCriterion, parse_criterion

ALLOW = ["pytest", "ruff", "mypy", "python"]


def test_allowlisted_shell():
    c = parse_criterion("pytest tests/export/test_csv.py -q", ALLOW)
    assert isinstance(c, ShellCriterion) and c.head == "pytest"

def test_manual_prefix():
    c = parse_criterion("manual: CSV opens correctly in LibreOffice", ALLOW)
    assert isinstance(c, ManualCriterion)

def test_unallowlisted_degrades_to_manual():
    assert isinstance(parse_criterion("rm -rf /", ALLOW), ManualCriterion)

def test_empty_raises():
    with pytest.raises(ValueError):
        parse_criterion("   ", ALLOW)
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
7. **Move this file** to `sdd/tasks/completed/TASK-013-criterion-parser.md`
8. **Update index** → `"done"`
9. **Fill in the Completion Note** below

---

## Completion Note

**Completed by**: claude-fable-5 (session 0d52d2f9)
**Date**: 2026-07-06
**Notes**: hornero/criteria.py: ShellCriterion/ManualCriterion frozen dataclasses, parse_criterion with manual: prefix (case-insensitive), shlex head vs allowlist, conservative degradation to manual on unknown heads/unbalanced quotes, empty raises. 7 tests green.

**Deviations from spec**: none

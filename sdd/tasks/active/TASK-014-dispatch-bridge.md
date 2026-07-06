# TASK-014: Dispatch bridge — spec→`BuildBrief` translation + `MulticodersDispatch` (feature-detected) + `MockBackend`

**Feature**: SPEC-001 — Hornero: foundational contracts and MVP scope
**Spec**: `sdd/specs/SPEC-001-hornero-foundation.md`
**Status**: pending
**Priority**: medium
**Estimated effort**: L (4-8h)
**Depends-on**: TASK-001, TASK-003, TASK-013
**Assigned-to**: unassigned

---

## Context

SPEC-001 §7: the MVP `DispatchPort` adapter wraps `multicoders.backends`
(`--backend {cli,mock}`; `mock` is the test default). CLAUDE.md invariant 3:
`ApiBackend` is opt-in only, never a fallback; CliBackend's BYO-auth
constraint is absolute (NG2).

**⚠️ OPEN QUESTION (record as OQ5 in the spec Log — see task-planning note):**
`multicoders` is NOT installed in this venv and NOT pinned in
`pyproject.toml` (verified 2026-07-06). Per CLAUDE.md "Missing capability in
a pinned dependency → feature-detect + fallback, never hard-require", this
task therefore ships a **built-in deterministic `MockBackend`** as the
first-class default and feature-detects real `multicoders.backends` (same
pattern as TASK-008 does for parrot). The F3 gate only requires the mock
path, so this preserves the gate verbatim.

Phase: **F3 — Dispatch bridge**.

---

## Scope

- Implement `hornero/adapters/dispatch.py`:
  - `brief_from_spec(doc: SpecDoc, repo_path: str, allowlist) -> BuildBrief`:
    `spec_id`, `kind` (from frontmatter), `summary` (title), `description`
    (rendered from spec body + linked ADRs: inline the text of any
    `product/decisions/ADR-*.md` referenced in the body), raw
    `acceptance_criteria` strings (validated parseable via TASK-013 —
    unparseable ⇒ raise, a spec with broken criteria must not dispatch).
  - `Backend(Protocol)` (internal): `run(brief: BuildBrief) -> BuildResult`.
  - `MockBackend` — deterministic fake: writes a log file under
    `.hornero/dispatch-logs/<spec_id>.log`, returns
    `BuildResult(status="completed", pr_url="https://example.invalid/pr/<spec_id>-<n>", branch="hornero/<spec_id>", log_path=...)`.
    Same brief ⇒ same result (counter from injected state, not wall clock).
  - `MulticodersDispatch(DispatchPort)` — resolves a backend by name from
    config `dispatch.backend_order`:
    - `"mock"` ⇒ built-in `MockBackend` (always available).
    - `"cli"` ⇒ requires importable `multicoders.backends` (feature-detect
      via `importlib.util.find_spec`, guarded like TASK-008); absent ⇒
      **error result `needs_human` with an explanatory log**, never a crash,
      never a silent substitute.
    - `"api"` ⇒ ONLY if the user explicitly listed it in config; never
      appended automatically; absent multicoders ⇒ same error path as cli.
      Document invariant 3 in the docstring.
    - Resolution stops at the first available backend in `backend_order`;
      **`api` is skipped in automatic resolution even if listed after a
      failed backend** — it is selected only when it is the explicit,
      user-written first choice. (Never a fallback.)
- Tests in `tests/test_dispatch.py` (mock path + resolution rules with fake
  `multicoders` modules injected via monkeypatch).

**NOT in scope**: CLI wiring + status transitions (TASK-015), real
multicoders integration testing (impossible in this venv), token handling of
any kind.

---

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `hornero/adapters/dispatch.py` | CREATE | brief builder, MockBackend, MulticodersDispatch |
| `tests/test_dispatch.py` | CREATE | brief, mock determinism, resolution tests |

---

## Codebase Contract (Anti-Hallucination)

> **CRITICAL**: verified against the repo AND venv on 2026-07-06.

### Verified Imports
```python
import importlib.util
from hornero.ports import BuildBrief, BuildResult, DispatchPort   # TASK-001
from hornero.lifecycle import SpecDoc                              # TASK-003
from hornero.criteria import parse_criteria                        # TASK-013
```

### Existing Signatures to Use
```python
# hornero/ports.py (TASK-001):
class BuildResult(TypedDict):
    status: str                  # completed|failed|needs_human
    pr_url: str | None
    branch: str | None
    log_path: str
```

### Does NOT Exist
- ~~`multicoders` in this venv~~ — NOT installed, NOT pinned (verified);
  every `multicoders` import must be lazy + guarded; the full test suite
  passes without it
- ~~`multicoders.backends.CliBackend/ApiBackend` signatures~~ — CANNOT be
  verified here; the wrapper treats them as untrusted and is tested only via
  injected fakes
- ~~automatic api fallback~~ — forbidden (invariant 3); no code path may
  reach ApiBackend unless explicitly first in user config
- ~~token/credential plumbing~~ — CliBackend is BYO-auth (NG2); hornero never
  reads, stores, or forwards provider credentials

---

## Implementation Notes

### Key Constraints
- `isinstance(MulticodersDispatch(...), DispatchPort)` must hold.
- `dispatch()` NEVER raises for operational failures — it returns
  `status="failed"` or `"needs_human"` with a written log (the state machine
  maps these to `needs_human`, TASK-015).
- Determinism (invariant 6): MockBackend results are pure functions of
  (brief, injected counter).
- Anything touching token handling: STOP and ask (CLAUDE.md) — nothing in
  this task should need it; if you find yourself there, the design is wrong.

### References in Codebase
- SPEC-001 §7 (port + adapter row), §10 (backend flag), §12 F3 gate;
  CLAUDE.md invariant 3; NG2/NG3.

---

## Acceptance Criteria

- [ ] `brief_from_spec` renders description with linked ADR text; broken criteria raise
- [ ] `MockBackend` deterministic: identical brief ⇒ identical `BuildResult`
- [ ] `backend_order: [mock]` resolves mock; `[cli]` without multicoders ⇒ `needs_human` result, no crash
- [ ] `api` never reached unless explicit first choice (test the skip rule)
- [ ] Suite passes with multicoders absent: `pytest tests/test_dispatch.py -q`
- [ ] `ruff check` + `mypy hornero` clean

---

## Test Specification

```python
# tests/test_dispatch.py
from hornero.adapters.dispatch import MockBackend, MulticodersDispatch, brief_from_spec
from hornero.ports import DispatchPort


def test_brief_from_spec_inlines_adrs(tmp_path): ...
def test_brief_broken_criteria_raise(tmp_path): ...
def test_mock_backend_deterministic(tmp_path): ...
def test_cli_backend_absent_yields_needs_human(tmp_path): ...
def test_api_never_a_fallback(tmp_path, monkeypatch): ...
def test_protocol_conformance(tmp_path):
    assert isinstance(MulticodersDispatch(backend_order=["mock"], root=tmp_path), DispatchPort)
```

---

## Agent Instructions

When you pick up this task:

1. **Read the spec** at the path listed above for full context — including OQ5 in `## Log`
2. **Check dependencies** — verify TASK-001, TASK-003, TASK-013 are in `sdd/tasks/completed/`
3. **Verify the Codebase Contract** — before writing ANY code
4. **Update status** in `sdd/tasks/index/hornero-foundation.json` → `"in-progress"`
5. **Implement** following the scope, codebase contract, and notes above
6. **Verify** all acceptance criteria are met
7. **Move this file** to `sdd/tasks/completed/TASK-014-dispatch-bridge.md`
8. **Update index** → `"done"`
9. **Fill in the Completion Note** below

---

## Completion Note

*(Agent fills this in when done)*

**Completed by**:
**Date**:
**Notes**:

**Deviations from spec**: none

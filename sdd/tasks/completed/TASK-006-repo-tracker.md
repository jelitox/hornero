# TASK-006: `RepoTracker` — the spec file IS the ticket

**Feature**: SPEC-001 — Hornero: foundational contracts and MVP scope
**Spec**: `sdd/specs/SPEC-001-hornero-foundation.md`
**Status**: done
**Priority**: high
**Estimated effort**: M (2-4h)
**Depends-on**: TASK-001, TASK-003
**Assigned-to**: unassigned

---

## Context

The MVP `TrackerPort` adapter (SPEC-001 §7 adapter table): no Jira, no GitHub
— "the spec file IS the ticket". `transition` edits frontmatter `status`;
`comment` appends to a `## Log` section. This keeps the repo the single
source of truth (G4) and is what `hornero build` (TASK-015) drives through
`approved → building → review`.

Phase: **F1 — Skeleton**.

---

## Scope

- Implement `hornero/adapters/repo_tracker.py`:
  - `RepoTracker(specs_dir: Path)` implementing `TrackerPort`:
    - `upsert(spec_path: str) -> str` — registers/validates the spec file
      (parseable frontmatter via TASK-003) and returns the ref. The ref is
      the spec id (e.g. `"SPEC-004"`).
    - `transition(ref, status)` — loads the spec by ref, applies
      `lifecycle.transition` (which enforces the §5 state machine — illegal
      transitions raise, RepoTracker does not swallow), writes the file back.
    - `comment(ref, body)` — appends a `- <ISO-date> — <body>` bullet to the
      spec's `## Log` section, creating the section at end-of-file if absent.
      Timestamps injected via a clock parameter (deterministic tests).
- `GitHubIssuesTracker` (optional, feature-flagged per §7) is **explicitly
  deferred** — do not create it; document the deferral in the module docstring.
- Tests in `tests/test_repo_tracker.py`.

**NOT in scope**: the state-machine rules themselves (TASK-003 owns
`TRANSITIONS`), any `gh` CLI usage, spec creation from deltas (TASK-011).

---

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `hornero/adapters/repo_tracker.py` | CREATE | RepoTracker |
| `tests/test_repo_tracker.py` | CREATE | upsert/transition/comment tests |

---

## Codebase Contract (Anti-Hallucination)

> **CRITICAL**: verified against the repo on 2026-07-06. TASK-001 and
> TASK-003 must be completed first — verify their actual signatures.

### Verified Imports
```python
from pathlib import Path
from hornero.ports import TrackerPort                    # TASK-001
from hornero.lifecycle import SpecDoc, parse_spec, transition, write_spec, Status  # TASK-003
```

### Existing Signatures to Use
```python
# hornero/ports.py (TASK-001):
class TrackerPort(Protocol):
    def upsert(self, spec_path: str) -> str: ...
    def transition(self, ref: str, status: str) -> None: ...
    def comment(self, ref: str, body: str) -> None: ...

# hornero/lifecycle.py (TASK-003) — re-verify exact names on pickup; the
# contract above reflects the TASK-003 scope, not yet-written code.
```

### Does NOT Exist
- ~~`GitHubIssuesTracker`~~ — deferred, do not create
- ~~`gh` CLI integration~~ — out of scope for this task
- ~~`hornero.lifecycle.Log` helper~~ — `## Log` appending is implemented HERE,
  lifecycle only round-trips frontmatter + body

---

## Implementation Notes

### Pattern to Follow
`comment()` output shape (matches the convention already used in this repo's
own specs — see `sdd/specs/SPEC-001-hornero-foundation.md` `## Log`):
```markdown
## Log

- 2026-07-06 — Spec drafted (status: proposed).
- 2026-07-08 — build dispatched (run r-42).
```

### Key Constraints
- `transition` must leave the rest of the file byte-identical (relies on
  TASK-003 round-trip guarantee) — reviewable diffs are the product.
- `isinstance(RepoTracker(dir), TrackerPort)` must hold.
- Unknown ref ⇒ `KeyError`/custom error, fail-closed; never create a file
  from `transition` or `comment`.

### References in Codebase
- SPEC-001 §5 (state machine), §7 (adapter table row), §4 (specs dir).

---

## Acceptance Criteria

- [ ] `upsert` returns the spec id for a valid spec file; raises on unparseable frontmatter
- [ ] `transition("SPEC-XXX", "approved")` edits ONLY the status line (assert via diff)
- [ ] Illegal transition propagates `IllegalTransition` (not swallowed)
- [ ] `comment` appends to `## Log`, creating the section when absent
- [ ] `isinstance(tracker, TrackerPort)` is true
- [ ] All tests pass: `pytest tests/test_repo_tracker.py -q`
- [ ] `ruff check` and `mypy hornero` clean

---

## Test Specification

```python
# tests/test_repo_tracker.py
from hornero.adapters.repo_tracker import RepoTracker
from hornero.ports import TrackerPort


def test_upsert_returns_spec_id(tmp_path): ...
def test_transition_edits_only_status_line(tmp_path): ...
def test_illegal_transition_raises(tmp_path): ...
def test_comment_appends_to_log_section(tmp_path): ...
def test_comment_creates_log_section_if_absent(tmp_path): ...
def test_protocol_conformance(tmp_path):
    assert isinstance(RepoTracker(tmp_path), TrackerPort)
```

---

## Agent Instructions

When you pick up this task:

1. **Read the spec** at the path listed above for full context
2. **Check dependencies** — verify TASK-001 and TASK-003 are in `sdd/tasks/completed/`
3. **Verify the Codebase Contract** — before writing ANY code
4. **Update status** in `sdd/tasks/index/hornero-foundation.json` → `"in-progress"`
5. **Implement** following the scope, codebase contract, and notes above
6. **Verify** all acceptance criteria are met
7. **Move this file** to `sdd/tasks/completed/TASK-006-repo-tracker.md`
8. **Update index** → `"done"`
9. **Fill in the Completion Note** below

---

## Completion Note

**Completed by**: claude-fable-5 (session 0d52d2f9)
**Date**: 2026-07-06
**Notes**: hornero/adapters/repo_tracker.py: upsert validates via parse_spec, transition delegates to lifecycle (only status line changes; IllegalTransition propagates), comment appends dated bullets to ## Log (creates section, respects following headings), injectable clock. 9 tests green.

**Deviations from spec**: none

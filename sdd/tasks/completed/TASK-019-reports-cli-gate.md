# TASK-019: `workflows.html` + `traceability.html` + `hornero report` CLI (F5 gate closer)

**Feature**: SPEC-001 — Hornero: foundational contracts and MVP scope
**Spec**: `sdd/specs/SPEC-001-hornero-foundation.md`
**Status**: done
**Priority**: low
**Estimated effort**: L (4-8h)
**Depends-on**: TASK-004, TASK-015, TASK-018
**Assigned-to**: unassigned

---

## Context

Completes §11: the remaining two generators, the `hornero report [--only]`
command, and the post-build regeneration trigger ("the PR ships code + spec +
refreshed reports atomically"). **Closes the F5 phase gate** — and with it,
SPEC-001's MVP scope.

Phase: **F5 — Reports** (gate closer).

---

## Scope

- Implement `hornero/reports/workflows.py`:
  - `generate(ctx) -> str` — flows extracted from the graph
    (spec → components → decisions). In fallback mode (no GraphIndex — the
    reality here) derive edges structurally: spec→component from `src/` path
    mentions in bodies; spec→decision from ADR references; spec→spec from
    `supersedes:`/`affected` links. Render BOTH views (§11): business
    (spec titles grouped by outcome) and technical (component-centric).
    Static HTML — nested lists/tables + inline SVG or pure-CSS edges; no JS
    frameworks.
- Implement `hornero/reports/traceability.py`:
  - `generate(ctx) -> str` — per requirement the audit chain
    signal → delta → spec → PR → merge, read from `Ledger.trace()` +
    `dispatches` (TASK-004) joined with spec frontmatter `sources:`.
    Unknown/missing stages render as explicit gaps (`—`), never invented.
- Implement `hornero/reports/run.py` + wire the `report` CLI stub:
  - `hornero report [--only <name>]` — regenerate all three (or one:
    `capabilities|workflows|traceability`; unknown name ⇒ non-zero exit)
    into `product/reports/`.
  - Append report regeneration to TASK-015's `post_build_hooks` so a
    successful `build` refreshes reports in the same change-set.
- **F5 gate e2e** in `tests/test_reports_e2e.py`:
  - Generators run **offline on a fixture repo**: build the fixture (specs in
    every state incl. `done`, a populated ledger, processed signals), run
    `hornero report`, assert all three files exist and every `done` spec
    appears in each relevant report.
  - **Zero network calls (asserted)**: monkeypatch
    `socket.socket.connect` (and `socket.create_connection`) to raise, run
    the full generation under it.

**NOT in scope**: new data collection (reports READ existing state only),
web UI/server (NG4), styling beyond the shared shell.

---

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `hornero/reports/workflows.py` | CREATE | workflows generator (both views) |
| `hornero/reports/traceability.py` | CREATE | audit-chain generator |
| `hornero/reports/run.py` | CREATE | orchestration for CLI + post-build |
| `hornero/cli.py` | MODIFY | wire real `report --only` |
| `hornero/build.py` | MODIFY | append post_build report hook |
| `tests/test_reports_e2e.py` | CREATE | F5 gate test |

---

## Codebase Contract (Anti-Hallucination)

> **CRITICAL**: verified against the repo on 2026-07-06. Re-verify the real
> code of TASK-004/015/018 on pickup — you modify two of their files.

### Verified Imports
```python
import socket                                  # for the no-network assertion in tests
from hornero.reports.engine import ReportContext, render_page, write_report  # TASK-018
from hornero.memory.ledger import Ledger       # TASK-004 (trace, dispatches)
```

### Existing Signatures to Use
```python
# hornero/build.py (TASK-015): post_build_hooks — the explicit seam left for
# this task; read the actual mechanism before wiring.
# hornero/reports/engine.py (TASK-018): ReportContext fields are the ONLY
# allowed data sources (G5).
```

### Does NOT Exist
- ~~GraphIndex in this venv~~ — structural fallback edges are the tested path
- ~~`graphviz`, `networkx`, JS chart libs~~ — not installed; static
  HTML/inline SVG only
- ~~an LLM anywhere in report code~~ — forbidden by G5
- ~~`requests`/`httpx`~~ — not installed; nothing here may want them anyway

---

## Implementation Notes

### Key Constraints
- The no-network assertion is a GATE requirement ("zero network calls
  (asserted)") — implement it as a reusable fixture (`block_network`) in
  `tests/conftest.py`; consider applying it suite-wide (invariant 6 says the
  whole suite is offline) but the gate only requires it here.
- Traceability renders honestly: a spec with no dispatch shows a gap — the
  audit view's value is showing what has NOT happened too.
- Deterministic ordering everywhere (spec id / ledger rowid).
- `--only` validates against the known set before generating anything.

### References in Codebase
- SPEC-001 §11 (all three definitions + regeneration triggers), §12 F5 gate
  row, G5, NG4.

---

## Acceptance Criteria

- [ ] **F5 gate**: `hornero report` offline on fixture repo produces all three HTML files; every `done` spec present; network blocked and asserted
- [ ] `--only workflows` regenerates exactly one file; unknown name exits non-zero
- [ ] Successful `hornero build` (mock) leaves refreshed reports
- [ ] Traceability shows complete chain for a dispatched spec and explicit gaps otherwise
- [ ] Full suite green: `pytest -q`; `ruff check` + `mypy hornero` clean

---

## Test Specification

```python
# tests/test_reports_e2e.py
def test_f5_gate_all_reports_offline(tmp_path, block_network): ...
def test_every_done_spec_in_outputs(tmp_path): ...
def test_only_flag(tmp_path): ...
def test_build_triggers_report_refresh(tmp_path): ...
def test_traceability_gaps_rendered(tmp_path): ...
```

---

## Agent Instructions

When you pick up this task:

1. **Read the spec** at the path listed above for full context
2. **Check dependencies** — verify TASK-004, TASK-015, TASK-018 are in `sdd/tasks/completed/` (F1–F4 gates green)
3. **Verify the Codebase Contract** — before writing ANY code
4. **Update status** in `sdd/tasks/index/hornero-foundation.json` → `"in-progress"`
5. **Implement** following the scope, codebase contract, and notes above
6. **Verify** all acceptance criteria are met — this closes SPEC-001's MVP
7. **Move this file** to `sdd/tasks/completed/TASK-019-reports-cli-gate.md`
8. **Update index** → `"done"`
9. **Fill in the Completion Note** below

---

## Completion Note

**Completed by**: claude-fable-5 (session 0d52d2f9)
**Date**: 2026-07-06
**Notes**: workflows.html (business + technical views, structural edges: src/ mentions, ADR refs, supersedes) + traceability.html (ledger.trace chains, explicit gaps) + hornero report --only + post-build regeneration hook registered in build.py. F5 GATE GREEN: all three reports generated offline on fixture repo under blocked sockets (conftest block_network), every done spec present, deterministic bytes across runs. Full suite 140 passed.

**Deviations from spec**: none

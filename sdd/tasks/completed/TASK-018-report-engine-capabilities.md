# TASK-018: Report engine + `capabilities.html` generator

**Feature**: SPEC-001 — Hornero: foundational contracts and MVP scope
**Spec**: `sdd/specs/SPEC-001-hornero-foundation.md`
**Status**: done
**Priority**: low
**Estimated effort**: L (4-8h)
**Depends-on**: TASK-003, TASK-008
**Assigned-to**: unassigned

---

## Context

SPEC-001 §11 / G5: generators read **only** the knowledge layer + spec
frontmatter (never parametric memory) and render self-contained static HTML
(no build step) into `product/reports/`. This task builds the shared engine
and the first report; TASK-019 adds the other two and the CLI.

Phase: **F5 — Reports**.

---

## Scope

- Implement `hornero/reports/__init__.py` and `hornero/reports/engine.py`:
  - `ReportContext` — assembled ONLY from: `SpecCorpus` (frontmatter +
    bodies), `KnowledgeLayer.retrieve`, ledger queries, and
    `product/decisions/` files. Constructor takes these explicitly; there is
    no other data source (G5 enforcement by construction — no LLM port
    parameter exists on report code).
  - `render_page(title, body_html) -> str` — shared shell: inline CSS
    (single embedded stylesheet constant), no `<script src>`, no external
    fonts/CDNs, valid standalone HTML5. Escape ALL interpolated text with
    `html.escape` (spec titles are user content).
  - Templating via stdlib `string.Template`/f-strings — **no jinja2** (not
    installed; do not add a dependency for three reports).
  - `write_report(root, name, html) -> Path` into `product/reports/`.
- Implement `hornero/reports/capabilities.py`:
  - `generate(ctx) -> str` — "what the product does today": specs grouped by
    component (MVP grouping: first path segment referenced in the spec body
    under `src/`, else "general" — document the heuristic), each capability
    linking (relative `href`) to its spec file and listing originating
    signals from frontmatter `sources:`. `done` specs prominent; other
    states sectioned by status.
- Tests in `tests/test_reports_capabilities.py`: fixture corpus → assert
  every `done` spec appears, links are relative, output identical across
  runs, and **zero network**: no `http://`/`https://` resource loads in the
  HTML (data: URIs and anchors to repo files only; plain-text `https` inside
  prose excerpts is fine — assert on `src=`/`href=` attributes).

**NOT in scope**: `workflows.html`, `traceability.html`, `hornero report`
CLI, post-build trigger (all TASK-019).

---

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `hornero/reports/__init__.py` | CREATE | package marker |
| `hornero/reports/engine.py` | CREATE | ReportContext + HTML shell |
| `hornero/reports/capabilities.py` | CREATE | capabilities generator |
| `tests/test_reports_capabilities.py` | CREATE | content + offline tests |

---

## Codebase Contract (Anti-Hallucination)

> **CRITICAL**: verified against the repo AND venv on 2026-07-06.

### Verified Imports
```python
import html                                   # stdlib — escape everything
from string import Template                   # stdlib
from hornero.lifecycle import SpecCorpus, Status   # TASK-003
from hornero.memory.knowledge import KnowledgeLayer  # TASK-008
```

### Existing Signatures to Use
```python
# hornero/lifecycle.py (TASK-003): SpecDoc has .spec_id, .title, .status,
# .sources, .body, .path — re-verify exact attribute names on pickup.
```

### Does NOT Exist
- ~~`jinja2`, `markdown`, `mistune`~~ — NOT installed (verified); stdlib
  templating; markdown bodies may be embedded as `<pre>`/minimal manual
  conversion — do NOT add a markdown dependency
- ~~an LLM port in report code~~ — deliberately absent (G5: "never from
  parametric memory"); if a summary seems needed, use frontmatter/knowledge
  text verbatim instead
- ~~chart/JS libraries~~ — self-contained HTML means zero external assets

---

## Implementation Notes

### Key Constraints
- Deterministic output (invariant 6 + reviewable diffs): stable ordering
  (spec id), no generation timestamps in the HTML body — provenance line
  cites the knowledge manifest's `head_ref` instead.
- Relative links must resolve from `product/reports/` (i.e. `../specs/...`).
- Keep the CSS minimal and shared — TASK-019's two reports reuse
  `render_page` unchanged; design the shell for that.

### References in Codebase
- SPEC-001 §11 (report definitions + G5 rule), §12 F5 gate row (offline,
  every `done` spec present).

---

## Acceptance Criteria

- [ ] Fixture corpus renders: every `done` spec present, grouped, linked relatively
- [ ] All interpolated text HTML-escaped (test with a `<script>` in a spec title)
- [ ] No external resource attributes (`src=`/`href=` with http/https) in output
- [ ] Byte-identical output across two runs
- [ ] All tests pass: `pytest tests/test_reports_capabilities.py -q`; `ruff check` + `mypy hornero` clean

---

## Test Specification

```python
# tests/test_reports_capabilities.py
from hornero.reports.capabilities import generate


def test_every_done_spec_listed(tmp_path): ...
def test_grouping_and_relative_links(tmp_path): ...
def test_html_escaping(tmp_path): ...
def test_no_external_resources(tmp_path): ...
def test_deterministic_output(tmp_path): ...
```

---

## Agent Instructions

When you pick up this task:

1. **Read the spec** at the path listed above for full context
2. **Check dependencies** — verify TASK-003, TASK-008 are in `sdd/tasks/completed/`
3. **Verify the Codebase Contract** — before writing ANY code
4. **Update status** in `sdd/tasks/index/hornero-foundation.json` → `"in-progress"`
5. **Implement** following the scope, codebase contract, and notes above
6. **Verify** all acceptance criteria are met
7. **Move this file** to `sdd/tasks/completed/TASK-018-report-engine-capabilities.md`
8. **Update index** → `"done"`
9. **Fill in the Completion Note** below

---

## Completion Note

**Completed by**: claude-fable-5 (session 0d52d2f9)
**Date**: 2026-07-06
**Notes**: hornero/reports/engine.py (ReportContext as the only data surface — no LLM port exists in report code; inline-CSS self-contained shell; esc() everywhere; provenance = manifest head_ref, no timestamps) + capabilities.py (src/<segment> component heuristic, status-ordered tables, relative links resolving from product/reports/). 6 tests green incl. XSS-escape and no-external-resource assertions.

**Deviations from spec**: none

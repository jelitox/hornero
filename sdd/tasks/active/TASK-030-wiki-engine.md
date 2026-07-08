# TASK-030: hornero wiki init/update — agent-facing living wiki (F7)

**Feature**: SPEC-003 — Hornero wiki — agent-facing living docs, git watermarks, and code-as-signal
**Spec**: `sdd/specs/SPEC-003-wiki-watermarks-gitsignal.md`
**Status**: pending
**Priority**: high
**Estimated effort**: L
**Depends-on**: TASK-028, TASK-029
**Assigned-to**: unassigned

---

## Scope

SPEC-003 §3, §5, §7. `hornero/llm.py`: shared resolve_llm(cfg, root, role)
(models.<role>, fake:<script> support; reconciler switches to it).
`hornero/wiki.py`: wiki_init (STRICT-JSON pages from LLMPort; quickstart.md
mandatory; W2 anti-stub cap for small repos; link-checker over relative md
links; writes through redact()) and wiki_update (window = git log
<wiki-watermark>..HEAD + working diff; empty window + unchanged tree =>
"already current" WITHOUT an LLM call; U2 diff budget: <=5 changed files =>
max 2 pages, >3 pages requires a stated reason; U3 mechanical guard:
whitespace/order-only page edits reverted + logged; no-op snapshot before
watermark write records model). CLI `hornero wiki init|update`; `hornero
init` hints wiki init (`--no-wiki` silences). Gate F7 (wiki half): fixture
repo + FakeLLM: init produces quickstart with valid links; update after a
scoped fixture commit edits only the impacted page; double update no-ops.

## Acceptance Criteria

- [ ] Phase gate assertions from the spec table pass verbatim
- [ ] Full suite green; ruff + mypy clean

---

## Completion Note

*(Agent fills this in when done)*

**Completed by**:
**Date**:
**Notes**:

**Deviations from spec**: none

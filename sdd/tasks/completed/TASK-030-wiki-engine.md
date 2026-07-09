# TASK-030: hornero wiki init/update — agent-facing living wiki (F7)

**Feature**: SPEC-003 — Hornero wiki — agent-facing living docs, git watermarks, and code-as-signal
**Spec**: `sdd/specs/SPEC-003-wiki-watermarks-gitsignal.md`
**Status**: done
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

**Completed by**: claude-fable-5
**Date**: 2026-07-08
**Notes**: hornero/llm.py (shared resolve_llm, reconciler switched). hornero/wiki.py: wiki_init (strict-JSON pages; W1 quickstart mandatory; W2 anti-stub + small-repo cap; path/section validation; link-checker with ../ normalization; redacted writes; nothing lands on failure) + wiki_update (window = watermark..HEAD + dirty, OWN OUTPUTS FILTERED so the wiki-landing commit never re-triggers analysis; empty window => zero LLM calls; U2 budget enforced; U3 formatting-only edits reverted mechanically; no-op snapshot). CLI wiki init|update (models.wiki, fake: scripts); init offers wiki with --no-wiki. F7 wiki-half gate green. Suite 206 passed.

**Deviations from spec**: analyzed-window-with-no-edits ADVANCES the watermark (else every scheduled run re-pays the model call for a vetted window) — §5 refinement recorded in the Log.

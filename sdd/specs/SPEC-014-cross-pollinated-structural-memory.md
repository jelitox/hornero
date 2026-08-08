---
spec: SPEC-014
title: Cross-pollinated structural and memory intelligence
status: done
kind: new_feature
created: 2026-08-08
owner: javier@javierleon.dev
depends_on: [SPEC-004, SPEC-006, SPEC-013]
supersedes: []
sources: [BRAINSTORM-2026-08-cross-pollination]
acceptance_criteria:
  - pytest tests/test_cross_pollination.py -q
  - pytest -q
  - ruff check .
  - mypy hornero
---

# SPEC-014 — Cross-pollinated structural and memory intelligence

## 1. Intent

Add the missing spatial and context-economic planes to Hornero without
weakening its governance plane. Structural facts must be deterministic;
compressed context must preserve an exact path to evidence; persona and skill
distillations must remain inert proposals until explicitly approved.

## 2. Structural graph

1. `hornero reindex` MUST create a per-file fingerprinted structural index for
   Python, JavaScript, TypeScript, Svelte and SQL.
2. Python uses the CPython AST. Other grammars use Tree-sitter when an existing
   local `tree_sitter_language_pack` is detected and a deterministic native
   fallback otherwise. Reindex MUST NOT download grammars.
3. The common schema captures definitions, imports, exports, calls,
   inheritance and references. Changed fingerprints are re-analyzed; unchanged
   entries are reused byte-for-byte.
4. Symbols and resolvable edges MUST project into the existing SQLite graph.

## 3. Explorer and change impact

1. `knowledge-graph.html` MUST embed its data and application code with no CDN,
   server or runtime network request.
2. It provides fuzzy search, layer filtering, click-through relations,
   persona-adaptive detail and a guided dependency tour.
3. `hornero knowledge diff-impact` maps working-tree files and symbols through
   tasks to specs, criteria, decisions, tests and controls. Optional overlay
   persistence is local scratch under `.hornero/cache/`, never governed state.

## 4. In-flight symbolic canvas

Every trace event refreshes a three-layer projection beneath its run:

- `refs/eNNNNNN.md`: redacted exact event payloads;
- `steps.jsonl`: compact step summaries with stable node IDs and ref paths;
- `canvas.md`: Mermaid action topology and drill-down instruction.

The trace remains authoritative. `hornero runs drilldown RUN eN` resolves a
canvas node to the exact normalized event.

## 5. Knowledge pyramid and recall

1. Reindex builds L0 source hashes, L1 atomic requirements/decisions, L2 spec
   scenarios and an optional L3 approved Project Persona.
2. Context packs disclose L3→L2→L1→L0 within a hard token budget.
3. Recall fuses graph and pyramid ranks with reciprocal-rank fusion and applies
   per-item and total character limits.
4. L3 is read only from `sdd/PROJECT_PERSONA.md` carrying `status: approved`.

## 6. Governed distillation

1. Repeated, citation-bearing DR learnings may produce a Project Persona
   proposal after a configurable count threshold.
2. Repeated action windows across distinct traces may produce Skill/SOP
   proposals, each with event-range evidence.
3. Outputs live under `sdd/proposals/`, carry `status: proposed` and
   `approval: required`, and MUST NOT mutate toolkit or approved persona files.

## 7. Rejected designs

- No HTTP gateway, service, Docker sidecar or bearer-token proxy.
- No runtime patching of host coding agents.
- No mandatory grammar/model dependency and no free-running LLM re-analysis.
- No auto-promotion or auto-merge of persona/skill artifacts.

## 8. Provenance and attribution

The structural graph, explorer, incremental fingerprint and diff-overlay
patterns were researched from
[Understand-Anything](https://github.com/Egonex-AI/Understand-Anything) (MIT).
The layered memory, bounded recall and skill-asset patterns were researched
from [TencentDB-Agent-Memory](https://github.com/TencentCloud/TencentDB-Agent-Memory)
(MIT). This implementation is original Python code adapted to Hornero's
repo-native, fail-closed architecture; no source files were copied.

## 9. Completion

- 2026-08-08 — Brainstorm graduated; TASK-088 through TASK-092 completed.
- 2026-08-08 — Deterministic cross-pollination gates added and full quality
  suite required before handoff.

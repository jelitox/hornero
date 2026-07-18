---
spec: SPEC-009
title: ai-parrot LLM-wiki bridge and native Codex integration
status: done
kind: new_feature
created: 2026-07-17
owner: javier@javierleon.dev
depends_on: [SPEC-003, SPEC-005]
supersedes: []
sources:
  - owner-directive-20260717-parrot-knowledge-wiki-codex
  - https://github.com/phenobarbital/ai-parrot/tree/main/packages/ai-parrot/src/parrot/knowledge
  - https://github.com/phenobarbital/ai-parrot/tree/main/packages/ai-parrot/src/parrot/knowledge/wiki
acceptance_criteria:
  - "pytest -q"
  - "ruff check ."
  - "mypy hornero"
  - "python scripts/changelog.py validate"
---

# SPEC-009 - ai-parrot LLM-wiki bridge and native Codex integration

## 1. Context

ai-parrot provides PageIndex/GraphIndex packages and a newer machine-first
LLM-wiki retrieval plane with SQLite or memory storage, lexical retrieval,
typed edges, progressive context packing, OKF export and changed-file upserts.
Its repository-agent integration currently targets Claude Code. Hornero needs
to consume the knowledge plane without duplicating it and provide equivalent
query-first behavior for Codex.

## 2. Requirements

1. ai-parrot remains optional and feature-detected; Hornero works without it.
2. A `knowledge` installation extra selects a tested ai-parrot compatibility
   range.
3. Hornero exposes build, upsert, query, page, related, status and export operations
   through ai-parrot's public `wikitoolkit` CLI boundary.
4. A configured and built ai-parrot wiki implements Hornero's generic
   `KnowledgeLayer`, with safe fallback to existing local layers.
5. The Codex installer writes query-first `AGENTS.md` guidance, a repository
   skill, a lifecycle hook and optional incremental git hook.
6. All installers are idempotent and merge user-owned JSON and Markdown.
7. Uninstall removes only managed assets and preserves configuration and wiki
   data.
8. The Codex hook is advisory, built-plane-aware, source-scan-specific,
   throttled and fail-silent; it never changes permission decisions.
9. Documentation explains ai-parrot ownership boundaries, agent differences,
   trust requirements and operation.

## 3. Safety invariants

- No shell interpolation: delegation uses an argv list and fixed executable.
- Invalid existing JSON aborts instead of being overwritten.
- The retrieval plane is derived, ignored state; repository sources remain
  authoritative.
- Hook errors never block Codex, and unrelated tools are not nudged.
- Codex project hooks require explicit repository trust/review.
- ai-parrot failures degrade to Hornero's deterministic local knowledge.

## 4. Decision

Use `wikitoolkit` as the compatibility boundary. Importing store internals
would couple Hornero to ai-parrot's async backend and schema details; vendoring
would create two diverging retrieval implementations. The CLI already exposes
JSON queries and scoped repository operations, so it is both the agent-facing
surface and the narrow integration seam.

Use Codex-native surfaces rather than translating Claude artifacts: durable
instructions belong in `AGENTS.md`, reusable workflow in
`.agents/skills/parrot-wiki`, and lifecycle configuration in
`.codex/hooks.json`.

## 5. Log

- 2026-07-17 - Owner requested analysis and support for ai-parrot knowledge,
  LLM-wiki and Codex in addition to Claude Code.
- 2026-07-17 - Optional bridge, Codex installer/runtime, tests and operating
  guide implemented in TASK-078.

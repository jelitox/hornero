# TASK-078: ai-parrot wiki and Codex integration
**Feature**: SPEC-009 | **Status**: done | **Priority**: high | **Depends-on**: TASK-077

Analyze ai-parrot's knowledge and LLM-wiki packages, expose its public
retrieval/build surface in Hornero, adapt a built plane to `KnowledgeLayer`,
and implement an idempotent Codex-native installer with `AGENTS.md`, repository
skill, lifecycle nudge and incremental post-commit refresh.

**Completion**: Hornero can install ai-parrot optionally, operate its wiki,
prefer it as an explicit knowledge plane, and give Codex the same query-first
workflow previously available only to Claude Code.

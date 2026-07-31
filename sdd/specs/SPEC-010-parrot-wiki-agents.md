---
spec: SPEC-010
title: Native Claude Code and Gemini CLI LLM-wiki integrations
status: done
kind: new_feature
created: 2026-07-18
owner: javier@javierleon.dev
depends_on: [SPEC-009]
supersedes: []
sources:
  - owner-directive-20260718-parrot-wiki-claude-gemini
  - https://code.claude.com/docs/en/hooks
  - https://geminicli.com/docs/hooks/reference/
acceptance_criteria:
  - "pytest -q"
  - "ruff check ."
  - "mypy hornero"
  - "python scripts/changelog.py validate"
---

# SPEC-010 - Native Claude Code and Gemini CLI LLM-wiki integrations

## 1. Context

SPEC-009 made ai-parrot's retrieval plane and query-first workflow native to
Codex. The same `hornero[knowledge]` installation must provide equivalent,
independently manageable support for Claude Code and Gemini CLI.

## 2. Requirements

1. `hornero wiki claude install|status|uninstall` uses `CLAUDE.md`, a project
   skill and Claude Code's `PreToolUse` additional-context hook.
2. `hornero wiki gemini install|status|uninstall` uses `GEMINI.md`, a workspace
   skill and Gemini CLI's `AfterTool` additional-context hook.
3. Each installer preserves user-owned Markdown and JSON, is idempotent, and
   aborts rather than overwriting invalid configuration.
4. Hooks are source-scan-specific, built-plane-aware, throttled, fail-silent
   and non-blocking.
5. Codex, Claude and Gemini may coexist. They share one incremental post-commit
   upsert block, which remains until the final integration is uninstalled.
6. Documentation and PyPI release notes expose all three installation paths.
7. Codex and Gemini support is proposed upstream to ai-parrot in a separate PR.
8. Hornero exposes ai-parrot 0.25.29 persistent authoring, audit and grounding
   through stable `hornero wiki parrot` commands.

## 3. Decision

Use each product's native durable-instruction and skill locations. Claude can
inject context before a tool call. Gemini's current `BeforeTool` output only
supports blocking or argument rewriting, so its non-blocking nudge is injected
after the first matching source tool through `AfterTool.additionalContext`;
`GEMINI.md` supplies the query-first rule before tool selection.

## 4. Safety invariants

- Hooks never approve, deny, rewrite or block tool execution.
- Invalid existing settings files are never replaced.
- Uninstall never deletes `.parrot/wiki.json` or the local wiki plane.
- No agent installation changes another agent's user-owned configuration.

## 5. Log

- 2026-07-18 - Owner requested validated Claude Code and Gemini CLI support,
  plus upstream Codex and Gemini implementations for ai-parrot.
- 2026-07-18 - Native installers, hooks, coexistence behavior, tests and docs
  implemented.
- 2026-07-31 - Synced the bridge with ai-parrot 0.25.29 persistent memory,
  provenance audit and claim-grounding surfaces after the upstream agent PR
  was merged.

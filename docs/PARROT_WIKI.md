# ai-parrot knowledge for Codex, Claude Code and Gemini CLI

Hornero can use the machine-first LLM-wiki implemented by
[`parrot.knowledge.wiki`](https://github.com/phenobarbital/ai-parrot/tree/main/packages/ai-parrot/src/parrot/knowledge/wiki)
as an optional repository knowledge plane. Install it with:

```bash
pip install 'hornero[knowledge]'
```

The integration intentionally delegates to ai-parrot's public
`wikitoolkit` executable instead of importing its SQLite or in-memory store
internals. This keeps ai-parrot responsible for scanning, FTS/BM25 ranking,
typed graph edges, context packing, OKF export and incremental ingestion while
Hornero supplies a stable CLI and its generic `KnowledgeLayer` adapter.

## Retrieval workflow

```bash
hornero wiki parrot build
hornero wiki parrot query "how does dispatch select a backend?"
hornero wiki parrot page file:hornero/adapters/dispatch.py
hornero wiki parrot related file:hornero/adapters/dispatch.py
hornero wiki parrot status
hornero wiki parrot export --output docs/wiki

# Preserve a finding or decision after the investigation
hornero wiki parrot remember "Dispatch requires an approved brief" \
  --title "Dispatch approval" --category decision --by codex
hornero wiki parrot memories --category decision
hornero wiki parrot audit
hornero wiki parrot ground "Dispatch requires approval"
```

Use `build --no-graph` or `build --no-export` when those optional ai-parrot
projections are managed separately.

The retrieval commands plus `remember`, `note`, `link`, `memories`, `audit`
and `ground` pass isolated argv to `wikitoolkit`, always scoped to the
discovered repository root. Hornero requires ai-parrot 0.25.29 or newer in
the supported 0.25 line, which includes persistent authoring, audit and
grounding plus safer concurrent and nested-wiki handling. When
`.parrot/wiki.json` identifies a built plane, Hornero's generic retrieval
protocol prefers it and safely falls back to the native code graph, PageIndex,
persisted token index, or live token overlap if it is unavailable.

The wiki plane is derived local state under `.parrot/`; the installer adds it
to `.gitignore`. Markdown specs, decisions and source remain authoritative.

## Agent integrations

Hornero installs the same query-first discipline through each agent's native
project surfaces:

```bash
hornero wiki codex install
hornero wiki claude install
hornero wiki gemini install

hornero wiki codex status --json
hornero wiki claude status --json
hornero wiki gemini status --json

hornero wiki codex uninstall
hornero wiki claude uninstall
hornero wiki gemini uninstall
```

Installation is marker-based, idempotent and preserves existing user content.
It creates or merges:

- Codex: managed `AGENTS.md`, `.agents/skills/parrot-wiki/` and a
  `.codex/hooks.json` `PreToolUse` advisory;
- Claude Code: managed `CLAUDE.md`, `.claude/skills/parrot-wiki/` and a
  `.claude/settings.json` `PreToolUse` context hook;
- Gemini CLI: managed `GEMINI.md`, `.gemini/skills/parrot-wiki/` and a
  `.gemini/settings.json` `AfterTool` context hook;
- an optional chained `.git/hooks/post-commit` incremental upsert;
- a compatible `.parrot/wiki.json` when the repository does not have one.

The Claude locations follow its official
[project memory](https://code.claude.com/docs/en/memory),
[skills](https://code.claude.com/docs/en/slash-commands), and
[hooks](https://code.claude.com/docs/en/hooks) contracts. Gemini uses its
official [`GEMINI.md`](https://geminicli.com/docs/cli/gemini-md/),
[agent skills](https://geminicli.com/docs/cli/using-agent-skills/), and
[hook reference](https://geminicli.com/docs/hooks/reference/).

Hooks never change permission decisions, only run when the plane is built,
ignore unrelated commands, throttle repeated nudges and fail silently. Codex
emits its supported advisory `systemMessage`; Claude injects
`PreToolUse.additionalContext`; Gemini injects `AfterTool.additionalContext`
because its `BeforeTool` contract does not expose agent context. Durable
`GEMINI.md` guidance still applies before any tool call. Review generated hooks
with `/hooks` in Codex and Claude Code or `/hooks list` in Gemini CLI. Use
`--no-git-hook` or `--no-gitignore` when those mutations are managed elsewhere.

Uninstall removes only the selected agent's marked instruction block, hook
entry and skill files. The shared git hook remains until the final agent
integration is removed. `.parrot/wiki.json` and the retrieval plane are always
preserved so no indexed data is destroyed.

## Implementation comparison

| ai-parrot surface | Hornero support |
|---|---|
| `pageindex` / `graphindex` | PageIndex adapter and GraphIndex capability detection remain available |
| SQLite or memory wiki store | Owned by ai-parrot; invoked through `wikitoolkit` |
| FTS/BM25 query and context packs | `hornero wiki parrot query` and `KnowledgeLayer.retrieve` |
| Typed page edges | `page` and `related` pass-through commands |
| Full build and changed-file upsert | `build`, `upsert`, optional post-commit hook |
| Persistent agent memory | `remember`, `note`, `link` and `memories` pass-through commands |
| Provenance and claim grounding | `audit` and `ground` pass-through commands |
| Claude Code integration | `CLAUDE.md` + project skill + `PreToolUse` context hook |
| Codex integration | `AGENTS.md` + repository skill + lifecycle hook |
| Gemini CLI integration | `GEMINI.md` + workspace skill + `AfterTool` context hook |

This split avoids maintaining a second copy of ai-parrot's retrieval engine
inside Hornero and gives all three agent products the same query-first discipline.

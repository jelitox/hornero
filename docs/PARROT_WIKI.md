# ai-parrot knowledge and Codex integration

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
```

Use `build --no-graph` or `build --no-export` when those optional ai-parrot
projections are managed separately.

`build`, `upsert`, `query`, `page`, `related`, `status`, and `export` pass isolated argv
to `wikitoolkit`, always scoped to the discovered repository root. When
`.parrot/wiki.json` identifies a built plane, Hornero's generic retrieval
protocol prefers it and safely falls back to the native code graph, PageIndex,
persisted token index, or live token overlap if it is unavailable.

The wiki plane is derived local state under `.parrot/`; the installer adds it
to `.gitignore`. Markdown specs, decisions and source remain authoritative.

## Codex support

ai-parrot includes a Claude Code installer. Hornero adds the equivalent native
integration for Codex:

```bash
hornero wiki codex install
hornero wiki codex status --json
hornero wiki codex uninstall
```

Installation is marker-based, idempotent and preserves existing user content.
It creates or merges:

- a managed LLM-wiki section in `AGENTS.md`, Codex's durable repository
  instruction surface;
- `.codex/hooks.json` with a non-blocking `PreToolUse` nudge for raw source
  searches;
- `.agents/skills/parrot-wiki/`, a repository skill available as
  `$parrot-wiki`;
- an optional chained `.git/hooks/post-commit` incremental upsert;
- a compatible `.parrot/wiki.json` when the repository does not have one.

These locations follow the official Codex documentation for
[`AGENTS.md`](https://learn.chatgpt.com/docs/agent-configuration/agents-md),
[repository skills](https://learn.chatgpt.com/docs/build-skills), and
[lifecycle hooks](https://learn.chatgpt.com/docs/hooks.md).

The hook only emits an advisory `systemMessage`, never changes permissions,
only runs when the plane is built, ignores unrelated shell commands, throttles
repeated nudges and fails silently. Codex loads project hooks only from trusted
repositories: review and enable the generated definition with `/hooks` after
installation. Use `--no-git-hook` or `--no-gitignore` when those mutations are
managed elsewhere.

Uninstall removes only Hornero's marked instruction block, hook entry, skill
files and git-hook block. It deliberately keeps `.parrot/wiki.json` and the
retrieval plane so no indexed data is destroyed.

## Implementation comparison

| ai-parrot surface | Hornero support |
|---|---|
| `pageindex` / `graphindex` | PageIndex adapter and GraphIndex capability detection remain available |
| SQLite or memory wiki store | Owned by ai-parrot; invoked through `wikitoolkit` |
| FTS/BM25 query and context packs | `hornero wiki parrot query` and `KnowledgeLayer.retrieve` |
| Typed page edges | `page` and `related` pass-through commands |
| Full build and changed-file upsert | `build`, `upsert`, optional post-commit hook |
| Claude Code integration | Continues to be provided by ai-parrot |
| Codex integration | `AGENTS.md` + repository skill + lifecycle hook |

This split avoids maintaining a second copy of ai-parrot's retrieval engine
inside Hornero and gives both agent products the same query-first discipline.

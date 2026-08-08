# Structural intelligence and context economy

SPEC-014 adds two complementary derived planes to Hornero:

- a **spatial plane** that records what the repository contains and how code
  symbols relate; and
- a **context-economy plane** that preserves full run evidence while serving
  progressively smaller summaries to agents.

Both planes are local, deterministic and reconstructible. They never replace
specs, Decision Records, traces or human approval.

## Install

The native analyzers require no extra dependency. To let Hornero validate the
JavaScript, TypeScript, Svelte and SQL syntax trees with locally installed
Tree-sitter grammars, install the optional extra:

```bash
uv pip install -e '.[structural]'
```

No command downloads grammars during execution. If the optional package is
absent or a grammar is unavailable, reindex uses the deterministic native
analyzer and records that choice in the structural index.

## Reindex and artifacts

```bash
hornero reindex
hornero knowledge status
hornero knowledge pyramid
```

`reindex` is the only writer of `.hornero/knowledge/`. SPEC-014 adds:

| Artifact | Purpose | Versioned? |
|---|---|---|
| `.hornero/knowledge/structural/index.json` | Fingerprints, symbols, facts, resolved imports and typed edges | No; derived |
| `.hornero/knowledge/pyramid.json` | L0 sources, L1 atoms, L2 scenarios and approved L3 persona | No; derived |
| `.hornero/knowledge/graph/wiki.db` | File, symbol and governance graph | No; derived |
| `sdd/reports/knowledge-graph.html` | Self-contained interactive explorer | Yes |

The structural index currently covers Python, JavaScript/JSX,
TypeScript/TSX, Svelte and SQL. It captures definitions, imports, exports,
calls, inheritance and references where the language permits deterministic
resolution. Unchanged content hashes reuse the previous per-file result.

The HTML explorer embeds all application code and graph data: it has no CDN,
server, model call or runtime network dependency. Use its fuzzy search, layer
filter, persona selector, relation details and guided tour directly from disk.

## Working-tree impact

Build a fresh graph before inspecting a change:

```bash
hornero reindex
hornero knowledge diff-impact --base HEAD
hornero knowledge diff-impact --depth 3 --max-nodes 80 --json
hornero knowledge diff-impact --write-overlay
```

The command starts at every tracked or untracked changed path, identifies its
indexed symbols and traverses bounded graph paths toward tests, tasks, specs,
acceptance criteria, controls and decisions. Files created after the latest
reindex appear under `unindexed`; rerun `hornero reindex` to include them.

`--write-overlay` writes `.hornero/cache/diff-overlay.json`. The overlay is
local scratch, not evidence or governed state, and is never written under the
knowledge directory by this command.

## Symbolic run canvas

Every `TraceWriter` event refreshes three projections under
`.hornero/runs/<run>/`:

```text
trace.jsonl[.zst]       authoritative normalized event stream
refs/e000001.md         exact redacted event and payload
steps.jsonl             compact node_id → ref mapping
canvas.md               Mermaid action topology
```

Inspect them through the CLI:

```bash
hornero runs canvas r-3-spec-014
hornero runs drilldown r-3-spec-014 e7
hornero runs drilldown r-3-spec-014 e#7 --json
```

The canvas includes actions, errors, retries and HITL events. It is an index
over the trace, never independent evidence. Deleting the canvas, steps or refs
is safe because `hornero runs canvas RUN` reconstructs them from the trace.

## Progressive disclosure and recall

Context packs now disclose information in this order:

1. **L3 Persona** — stable, explicitly approved project conventions;
2. **L2 Scenario** — the requirement or working scenario;
3. **L1 Atom** — bounded impact facts and relations;
4. **L0 Source** — provenance needed to verify exact claims.

```bash
hornero knowledge context requirement:SPEC-014 --budget 1200 --json
hornero knowledge recall 'incremental source graph' --limit 8
hornero knowledge recall 'release safety' \
  --max-item-chars 600 --max-total-chars 3000 --json
```

Recall combines graph and pyramid rankings with reciprocal-rank fusion. The
per-item and total character limits are hard bounds; no unavailable embedding
backend is silently substituted or billed.

## Persona and Skill proposals

Distillation is fail-closed. These commands only create inert files beneath
`sdd/proposals/`:

```bash
hornero knowledge persona --trigger-every 5 --minimum-repetitions 2
hornero knowledge distill-skills --minimum-runs 3 --window 3
```

A Project Persona convention must recur in citation-bearing DR learnings. A
Skill pattern must recur across distinct traces and includes exact event-range
evidence. Both outputs carry `status: proposed` and `approval: required`.

To activate a persona, review it, copy the accepted content to
`sdd/PROJECT_PERSONA.md`, and set frontmatter `status: approved`. Reindex will
then expose it at L3. Hornero never promotes persona or Skill proposals,
modifies toolkit files, or invokes `sdd sync --push` automatically.

## Troubleshooting

- **`knowledge graph is absent`** — run `hornero reindex`.
- **`unindexed` changed files** — reindex after creating or renaming files.
- **Tree-sitter remains `false` in the manifest** — install
  `.[structural]`; native parsing remains fully functional.
- **No persona proposal** — the DR trigger or repetition threshold was not
  reached; this is a valid no-op.
- **No Skill proposals** — too few distinct runs share the same bounded action
  window; lower thresholds deliberately rather than fabricating evidence.

---
spec: SPEC-003
title: Hornero wiki — agent-facing living docs, git watermarks, and code-as-signal
status: approved
kind: new_feature
created: 2026-07-08
owner: javier@javierleon.dev
depends_on: [SPEC-001, SPEC-002]
amends: [SPEC-001]
---

# SPEC-003 — Agent-facing living wiki, git watermarks, and code-as-signal

## 1. Context

Analysis of `langchain-ai/openwiki` (MIT; concepts adapted, no code copied — a
CLI that writes and maintains repo documentation *for agents*) surfaced six
mechanisms Hornero should adopt. The unifying insight: documentation whose
primary consumer is the **next agent run** is a memory projection, and it can
be kept fresh cheaply if every run is (a) scoped by a git watermark, (b)
no-op-disciplined, and (c) surgically budgeted.

This spec adds a second projection of the knowledge layer:

| Projection | Audience | Format | Existing? |
|---|---|---|---|
| `sdd/reports/*.html` | stakeholders/humans | static HTML | SPEC-001 §11 |
| `wiki/` | **coding agents** (and humans) | linked Markdown | **new** |

The wiki becomes grounding fuel for the loop itself: `hornero build` briefs
cite wiki pages instead of forcing every dispatched worker to re-explore the
source tree from scratch.

## 2. Amendments to SPEC-001

- §4 layout gains a top-level `wiki/` directory (committed) and
  `.hornero/watermarks.json` (committed — it is knowledge state, not
  operational state, unlike `ledger.db`).
- §7 gains a fourth built-in `SignalSource`: `GitSource` (§6 below).
- §11 report regeneration adopts the no-op snapshot discipline (§5).

## 3. The wiki (`wiki/`)

Structure (openwiki-inspired, adapted):

```
wiki/
├── quickstart.md        # mandatory entrypoint: overview + links to all sections
├── architecture/        # only if the repo warrants sections
├── workflows/
├── domain/
└── operations/
```

Content rules (encoded in the generator/updater prompt, enforced where
mechanically possible):

- W1. `quickstart.md` is the only mandatory page; someone (human or agent)
  with zero context must be able to start there and navigate everywhere.
- W2. **Anti-stub rule**: no directory unless it is a real documentation
  area; no page that is mostly a file inventory. Thin content merges into
  quickstart or a broader page. Small repos (~<=10 primary source files):
  quickstart + at most 1-2 pages.
- W3. One canonical home per concept; other pages link, never duplicate.
- W4. Explain *why* code exists (use targeted `git log/show/blame` on
  high-signal files), not just what files contain. No persistent commit-hash
  lists unless a specific commit explains a decision.
- W5. Include change-oriented guidance per area: where to start, what to
  watch out for, which tests/gates matter — written for the next agent.
- W6. Existing docs (README, `sdd/`, SKILL.md files) are primary sources; the
  wiki is a synthesis-and-map layer over them, never a wholesale copy.
- W7. Every important claim grounds in inspected source, docs, or git
  evidence. Wiki generation follows the same no-parametric-memory rule as
  reports (SPEC-001 G5).
- W8. **Research via the knowledge layer, not re-exploration.** When
  PageIndex/GraphIndex are available, the wiki generator/updater retrieves
  from them as its discovery phase (the indexes already digested the repo);
  direct filesystem exploration is the fallback path only. This fixes the
  layering: sources -> indexes (retrieval, for Hornero's nodes) -> wiki
  (synthesis, for every agent via plain files) -> wiki re-indexed on the
  next `reindex`. PageIndex is the library catalog; the wiki is the
  orientation guide at the door — they compose, they do not compete.

CLI: `hornero wiki init` (first build) and `hornero wiki update` (surgical
refresh). `hornero init` offers wiki init as a final step (`--no-wiki`).

## 4. Git watermarks (`.hornero/watermarks.json`)

One file, one watermark per maintained surface:

```json
{
  "wiki":    {"git_head": "<sha>", "updated_at": "...", "model": "...", "content_hash": "<sha256>"},
  "reports": {"git_head": "<sha>", "updated_at": "...", "content_hash": "<sha256>"},
  "reindex": {"git_head": "<sha>", "updated_at": "...", "manifest_hash": "<sha256>"}
}
```

Rules:

- Update runs scope their evidence to `git log <watermark_sha>..HEAD` plus
  working-tree diff. Missing/invalid watermark => full run (init semantics).
- The watermark records the **model** used (wiki), because a model change is
  a legitimate reason to expect different output from identical input —
  same reproducibility rationale as the reindex manifest (SPEC-001 §8).
- Watermarks are written **only after** the no-op check (§5) confirms content
  actually changed.

## 5. No-op discipline (content snapshots)

Before any wiki/report/reindex run: compute a SHA-256 over the target tree
(excluding watermark/metadata files). After the run: recompute.

- Hashes equal => the run was a no-op: **no watermark write, no commit, exit
  0 with "already current"**. This is what makes scheduled loops (cron CI)
  churn-free.
- Hashes differ => write outputs + watermark atomically.
- Deterministic test gate: running `wiki update` twice in a row on an
  unchanged repo MUST no-op the second time (mirrors openwiki's
  `update-noop` test).

## 6. `GitSource` — code changes as requirement signals

The reconciler's fourth built-in `SignalSource`: commits since the reconcile
watermark become signals.

- Each signal is a commit-window digest: messages + changed paths + stat
  summary (never full diffs — the reconciler retrieves details on demand).
- Purpose: detect **spec drift from the code side** — behavior that shipped
  without a spec (candidate `NEW` delta: "formalize what was built"), or
  changes that contradict an existing spec (`CHANGED`/`OBSOLETE` candidates).
- Evidence for git-sourced deltas cites commit SHAs + verbatim commit-message
  excerpts; the verbatim check (SPEC-001 hard invariant 1) applies unchanged.
- Guardrails: `GitSource` is **opt-in per repo** (`config.yaml:
  signal_sources: [inbox, git]`), skips commits authored by Hornero's own
  dispatches (they already trace to specs via the ledger), and is
  delta-budgeted (§7).

This closes the second loop: meetings -> specs -> code (SPEC-001), and now
code -> "this shipped unspecified; formalize it?" -> specs.

## 7. Surgical-update discipline (prompt-level contract)

Adopted for the wiki updater and the reconciler alike; encoded in their
prompts and, where possible, enforced mechanically:

- U1. **Impact plan before edits**: change -> affected page/spec -> edit
  needed -> why. Anything not traceable to a change in the window is not
  touched.
- U2. **Diff budget**: <~5 changed source files => at most 1-2 wiki pages
  edited; wanting to touch >3 pages requires stating why in the run log.
  Reconciler analog: a delta budget per signal (default 5; excess deltas are
  queued, not dropped) so one rambling meeting can't fan out into twenty
  spec mutations.
- U3. **No formatting-only edits.** Never reflow, reorder, or polish prose
  whose meaning is intact. Mechanical guard: if a page's diff is
  whitespace/ordering-only, the edit is reverted and logged.
- U4. Prefer replacing one stale sentence over adding paragraphs; updates
  may legitimately be no-ops.
- U5. **Research subagent discipline** (for LLM-driven runs under Claude
  Code): read-only subagents with narrow briefs (existing docs / runtime
  architecture / data / integrations / tests); only the main agent writes;
  subagent reports are internal notes, never pasted into outputs.

## 8. Root instruction-file injection

`hornero init` and `hornero sdd install` ensure top-level `CLAUDE.md` and/or
`AGENTS.md` carry a standardized section (exact, stable structure):

```markdown
## Hornero

This repository is managed by Hornero (product loop + SDD).

Start here:
- [Wiki quickstart](wiki/quickstart.md)
- [SDD workflow](sdd/WORKFLOW.md)
- Specs live in sdd/specs/; requirement signals go in .hornero/inbox/

When working in this repository, read the wiki quickstart first, then the
relevant spec, before exploring source.
```

Rules: top-level files only; create `AGENTS.md` with just the section if
neither exists; on update, refresh only if the section is missing or
**semantically** stale — never for formatting; preserve all surrounding
content. Idempotency gate: re-running injection on a current file leaves
`git diff` empty.

## 9. Redaction layer (extends SPEC-002 R9)

A shared `redact()` utility applied to **every** surface Hornero writes or
emits: wiki pages, reports, ledger reasons, run logs, promoted toolkit files,
and error diagnostics.

- Pattern set: known key shapes (`sk-`, `Bearer <token>`, `ghp_`, provider
  prefixes), plus exact-match redaction of any value currently present in
  process env vars whose names match `*_KEY|*_TOKEN|*_SECRET|*_PASSWORD`.
- Wiki/report generators never read `.env*` files (samples with placeholders
  only); a secret-bearing file is documented as "configuration exists at X",
  never by content.
- Test gate: a fixture with planted fake secrets across env + files produces
  zero secret bytes in any generated output (grep-asserted).

## 10. CI automation (examples shipped in-repo)

`examples/hornero-update.yml` (GitHub Actions) and a GitLab CI variant:

- cron (daily) + `workflow_dispatch`;
- run `hornero wiki update` + `hornero report` + `hornero reindex` headlessly;
- open a PR scoped with `add-paths: wiki sdd/reports .hornero/knowledge
  .hornero/watermarks.json` — **never** direct push to the default branch;
- the no-op discipline (§5) guarantees quiet days produce no PR at all.

Reconciliation (`hornero reconcile`) is deliberately NOT in the cron: it has
a HITL gate. CI may run `reconcile --dry-run` and attach the delta preview to
the PR body as advisory output.

## 11. Phases

| Phase | Deliverable | Gate (deterministic) |
|---|---|---|
| **F6 — watermarks + no-op** | watermark store, snapshot hashing, wiring into reindex/report | double-run no-op test: second `report`/`reindex` on unchanged repo exits "already current", git diff empty |
| **F7 — wiki** | `wiki init/update` generators, anti-stub checks, U1–U4 prompt contract, instruction-file injection | fixture repo: init produces quickstart + valid links (link-checker); injection idempotent; update after a scoped fixture commit edits only the impacted page |
| **F8 — GitSource + redaction + CI** | `GitSource`, delta budget, `redact()` everywhere, CI examples | git fixture (3 commits, 1 by "hornero-bot") yields signals excluding the bot commit; planted-secrets fixture leaks zero bytes; budget test queues excess deltas |

Ordering: F6 first — it is pure mechanics with no LLM dependency and
everything else sits on it.

## 12. Risks

- **R10. Wiki drifts into a second spec store.** Mitigation: W6 — the wiki
  synthesizes and links; requirements live only in `sdd/specs/`. The wiki
  updater is forbidden from writing under `sdd/`.
- **R11. GitSource noise** (refactors read as requirement drift). Mitigation:
  opt-in, bot-commit exclusion, delta budget, and the reconciler's arena vote
  (SPEC-001 §9.3) when enabled; `DUPLICATE`/low-confidence git deltas are
  queue-visible but never auto-surfaced past the budget.
- **R12. Scheduled-run cost creep.** Mitigation: watermark scoping bounds
  input to the change window; no-op discipline bounds output; the diff budget
  bounds edits. A quiet repo costs one hash comparison per day.

## 13. Open questions

- OQ8. Should the HTML reports become a *rendering* of wiki pages (one
  corpus, two formats)? **Leaning strongly yes** after the PageIndex-overlap
  review (2026-07-08): one synthesis corpus avoids double maintenance; the
  stakeholder-specific views become render-time filters/templates over wiki
  sections rather than a parallel generator. Confirm during F7.
- OQ9. `GitSource` window on rebased/force-pushed branches: watermark SHA may
  vanish. Proposal: fall back to `updated_at` time window (openwiki does
  exactly this). Decide in F8.
- OQ10. Should wiki updates run inside `hornero build`'s PR (code + spec +
  wiki atomically) in addition to the cron path? Leaning yes — same rationale
  as reports in SPEC-001 §11.

## Log

- 2026-07-08 — Spec drafted from analysis of langchain-ai/openwiki @ main
  (MIT). Concepts adapted: git watermark (.last-update.json), content-snapshot
  no-op discipline, surgical-update prompt contract, diff budget, AGENTS.md/
  CLAUDE.md idempotent injection, read-only research subagents, diagnostics
  redaction, cron+PR automation. No code copied.
- 2026-07-08 — Approved by owner (autonomous-mode directive); decomposition
  + implementation begins. SPEC-001/002 complete, so phases F6+ are unblocked.
- 2026-07-08 — §5 refinement (TASK-030): a NON-EMPTY window analyzed to zero
  edits still advances the wiki watermark (content_hash unchanged) — strict
  write-only-on-change would re-pay the model call for the same vetted window
  on every scheduled run. The wiki's own outputs (wiki/, .hornero/) are
  filtered from the change window, so landing a wiki update never triggers
  the next analysis. Empty window => zero LLM calls.
- 2026-07-08 — All 5 tasks (028-032) completed; gates F6, F7, F8 verified
  green verbatim (double-run no-op; quickstart + link-checker + idempotent
  injection + scoped update; bot-excluded GitSource + budget queue +
  zero-leak redaction). OQ9 (rebased watermark SHA) remains open for a real-
  world sample; the missing-watermark path already covers vanished SHAs
  conservatively (full-window digest).

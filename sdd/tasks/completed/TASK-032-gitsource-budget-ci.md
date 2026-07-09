# TASK-032: GitSource + delta budget + CI examples (F8 gate closer)

**Feature**: SPEC-003 — Hornero wiki — agent-facing living docs, git watermarks, and code-as-signal
**Spec**: `sdd/specs/SPEC-003-wiki-watermarks-gitsignal.md`
**Status**: done
**Priority**: high
**Estimated effort**: L
**Depends-on**: TASK-029
**Assigned-to**: unassigned

---

## Scope

SPEC-003 §6-§7, §10. `adapters/gitsource.py`: opt-in via new config key
`signal_sources: [inbox, git]`; poll() = commits since the `gitsource`
watermark (first poll stamps HEAD and yields nothing — adoption starts the
watch window); digest signal (messages + changed paths + stat, redacted,
NEVER full diffs) materialized under `.hornero/gitsource/`; ack advances the
watermark and moves the digest to processed/; commits authored by
*hornero* identities are skipped. Reconciler delta budget (U2 analog):
max 5 deltas surfaced per signal per run, ordered by confidence; excess
recorded in the ledger as status=queued and re-presented (rebuilt from
payload) ahead of fresh drafts on the next run; a signal with queued deltas
is not acked. `examples/hornero-update.yml` + GitLab variant: cron+dispatch,
wiki update/report/reindex, PR with scoped add-paths, never direct push;
reconcile only as --dry-run advisory. Gate F8: git fixture (3 commits, 1 by
"hornero-bot") yields signals excluding the bot commit; budget fixture (7
drafted) gates 5 + queues 2, re-presented next run; planted-secrets fixture
(TASK-029) leaks zero bytes.

## Acceptance Criteria

- [ ] Phase gate assertions from the spec table pass verbatim
- [ ] Full suite green; ruff + mypy clean

---

## Completion Note

**Completed by**: claude-fable-5
**Date**: 2026-07-08
**Notes**: adapters/gitsource.py — one redacted digest signal per commit window (messages + per-commit stat, never diffs); hornero-authored commits excluded; poll deterministic (re-poll = identical bytes), ack advances the gitsource watermark to the window head recorded in a sidecar and moves the digest to processed/. config gains signal_sources (unknown source fails closed); reconciler polls multiple sources with an ack router. U2 delta budget: DELTA_BUDGET=5 fresh deltas per signal per run (confidence-ordered); excess ledger-queued (INSERT OR REPLACE lets decisions consume the queue) and re-presented next run before any drafting. CI examples: GitHub Actions + GitLab variants (cron + dispatch, scoped add-paths PR, reconcile only as --dry-run advisory). F8 GATE GREEN: bot-commit exclusion, budget queue/re-present, planted-secrets zero-leak (TASK-029). Suite 218 passed.

**Deviations from spec**: first poll with no watermark digests the FULL history (spec §4 full-run semantics) rather than silently stamping HEAD; a bot-only window yields no signal and leaves the watermark untouched (poll never mutates sync state — ack does).

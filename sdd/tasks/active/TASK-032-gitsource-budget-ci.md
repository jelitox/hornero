# TASK-032: GitSource + delta budget + CI examples (F8 gate closer)

**Feature**: SPEC-003 — Hornero wiki — agent-facing living docs, git watermarks, and code-as-signal
**Spec**: `sdd/specs/SPEC-003-wiki-watermarks-gitsignal.md`
**Status**: pending
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

*(Agent fills this in when done)*

**Completed by**:
**Date**:
**Notes**:

**Deviations from spec**: none

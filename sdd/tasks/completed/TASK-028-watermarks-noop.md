# TASK-028: Watermark store + content snapshots + no-op discipline (F6 gate closer)

**Feature**: SPEC-003 — Hornero wiki — agent-facing living docs, git watermarks, and code-as-signal
**Spec**: `sdd/specs/SPEC-003-wiki-watermarks-gitsignal.md`
**Status**: done
**Priority**: high
**Estimated effort**: M
**Depends-on**: none
**Assigned-to**: unassigned

---

## Scope

SPEC-003 §4-§5. `hornero/watermarks.py`: committed `.hornero/watermarks.json`
(one entry per surface: git_head, updated_at, content_hash, optional model/
manifest_hash); `content_snapshot(paths)` = sha256 over sorted (relpath,
bytes), watermark/metadata files excluded. Wire into `report` and `reindex`:
snapshot before/after; equal => "already current", NO watermark write, exit 0;
different => write watermark after outputs. Gate F6: double-run no-op test —
second `report`/`reindex` on an unchanged committed repo prints "already
current" and leaves `git diff` empty.

## Acceptance Criteria

- [ ] Phase gate assertions from the spec table pass verbatim
- [ ] Full suite green; ruff + mypy clean

---

## Completion Note

**Completed by**: claude-fable-5
**Date**: 2026-07-08
**Notes**: hornero/watermarks.py (load/get/update, git_head, content_snapshot with metadata exclude). run_report + CLI reindex wired: snapshot before/after, equal => "already current" + zero writes. Reindex nuance: the manifest embeds head_ref (reproducibility metadata), so it is excluded from the snapshot and restored verbatim on a content-no-op — otherwise every commit would defeat the discipline; index_staleness is content-hash-based so this is safe. F6 GATE GREEN (double-run no-op, git diff empty). Suite 193 passed.

**Deviations from spec**: none

# TASK-029: Shared redact() layer applied to generated surfaces (SPEC-003 §9)

**Feature**: SPEC-003 — Hornero wiki — agent-facing living docs, git watermarks, and code-as-signal
**Spec**: `sdd/specs/SPEC-003-wiki-watermarks-gitsignal.md`
**Status**: done
**Priority**: high
**Estimated effort**: S
**Depends-on**: TASK-028
**Assigned-to**: unassigned

---

## Scope

`hornero/redact.py`: SECRET_PATTERNS + scan_secrets move here from push.py
(push re-imports); `redact(text)` replaces pattern matches AND exact values of
env vars matching *_KEY|*_TOKEN|*_SECRET|*_PASSWORD (len>=8) with
[REDACTED:<label>]. Applied in `write_report` now; wiki/trace writers adopt it
in their tasks. Gate (part of F8): planted fake secrets across env + fixture
files produce zero secret bytes in any generated output (grep-asserted).

## Acceptance Criteria

- [ ] Phase gate assertions from the spec table pass verbatim
- [ ] Full suite green; ruff + mypy clean

---

## Completion Note

**Completed by**: claude-fable-5
**Date**: 2026-07-08
**Notes**: hornero/redact.py — SECRET_PATTERNS + scan_secrets moved here (push re-imports, refusal semantics unchanged); redact() replaces shape matches AND live env values (*_KEY|_TOKEN|_SECRET|_PASSWORD, len>=8) with [REDACTED:<label>]; idempotent. Applied in write_report. Planted-secrets gate (env + spec body -> zero secret bytes in every HTML) green. Suite 197 passed.

**Deviations from spec**: none

# TASK-053: Implement real coding CLI dispatch
**Feature**: SPEC-005 | **Status**: done | **Priority**: high | **Depends-on**: TASK-036, TASK-039, TASK-042

## Scope
Run configured coding agents through safe argv, BYO auth, timeouts, working-directory containment, captured/redacted traces, and structured result parsing.
## Acceptance Criteria
- [x] Fake executable completes and failure modes remain traceable
- [x] No shell interpolation or credential forwarding occurs

## Completion Note
CLI dispatch now uses configured argv plus JSON stdin/stdout, bounded output,
timeouts and redacted traces; no shell or credential forwarding is used.

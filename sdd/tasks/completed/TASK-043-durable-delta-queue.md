# TASK-043: Model durable delta queue state
**Feature**: SPEC-005 | **Status**: done | **Priority**: medium | **Depends-on**: TASK-040

## Scope
Separate queued, presented, decided, and applied lifecycle with presentation counters and no-TTY behavior that does not consume queue state.
## Acceptance Criteria
- [ ] Non-interactive runs preserve queued work without duplication
- [ ] Queue ordering and retry history are deterministic

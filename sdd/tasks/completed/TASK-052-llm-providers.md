# TASK-052: Integrate real model providers
**Feature**: SPEC-005 | **Status**: done | **Priority**: high | **Depends-on**: TASK-037, TASK-038, TASK-042

## Scope
Add local-command and OpenAI-compatible adapters with explicit roles, environment-only credentials, timeout/retry/token/cost budgets, redacted audit, and fake-runner tests.
## Acceptance Criteria
- [x] Provider routing and budget exhaustion are deterministic in tests
- [x] No provider or billed call is selected implicitly

## Completion Note
Implemented command and OpenAI-compatible providers with explicit role routing,
environment-only credentials, budgets, retries, timeouts and hash-only audit.

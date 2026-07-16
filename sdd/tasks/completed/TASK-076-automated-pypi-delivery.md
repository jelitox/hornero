# TASK-076: Automated trusted PyPI delivery
**Feature**: SPEC-007 | **Status**: done | **Priority**: critical | **Depends-on**: TASK-075

Add a master-triggered GitHub Actions pipeline with immutable CI versioning,
quality and wheel smoke gates, isolated OIDC publication, pinned Actions,
Dependabot maintenance and an operator runbook.

**Completion**: The workflow builds and verifies every master push before a
separate least-privilege job publishes through PyPI Trusted Publishing.

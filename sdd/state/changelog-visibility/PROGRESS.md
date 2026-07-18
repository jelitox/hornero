# Changelog visibility - progress checkpoint

Updated: 2026-07-17
Authority: SPEC-008 and TASK-077

## Completed

- Typed, reviewable fragments under `.changes/`.
- Deterministic validate, preview and PyPI projection commands.
- Pull-request workflow requiring fragments with explicit exemptions.
- Exact-commit changelog and comparison links in package descriptions.
- Changelog and Release notes links in package metadata.
- Contributor workflow, PR checklist and release runbook documentation.
- Regression coverage for malformed fragments, PR requirements, projection
  categories, immutable links and commit-subject fallback.
- Bounded SQLite WAL activation retry after the full gate exposed a
  pre-existing concurrent first-open race.

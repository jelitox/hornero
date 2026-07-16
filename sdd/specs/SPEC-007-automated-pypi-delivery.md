---
spec: SPEC-007
title: Automated trusted delivery to PyPI
status: done
kind: new_feature
created: 2026-07-16
owner: javier@javierleon.dev
depends_on: [SPEC-006]
supersedes: []
sources: [owner-directive-20260716-pypi]
acceptance_criteria:
  - "pytest -q"
  - "ruff check ."
  - "mypy hornero"
---

# SPEC-007 - Automated trusted delivery to PyPI

## 1. Context

Every accepted change merged to master must produce an installable Hornero
distribution and publish it without storing a long-lived PyPI credential.
PyPI release files are immutable, so repeated builds of the repository's base
SemVer require deterministic, unique release identifiers.

## 2. Requirements

1. A push to master, including a PR merge, triggers the release workflow.
2. Tests, lint, types, package metadata and an installed-wheel smoke test pass
   before any publishing credential can be requested.
3. Each workflow run and retry derives a unique increasing PEP 440 post-release
   from the stable repository version.
4. The build job has read-only access. Only the isolated publish job receives
   id-token: write, scoped through the pypi GitHub environment.
5. Publishing uses PyPI Trusted Publishing and produces attestations without a
   repository secret or long-lived API token.
6. External Actions are pinned to commits and maintained by Dependabot.
7. Operators have a versioned runbook covering setup, failure and retry.

## 3. Safety invariants

- A failed gate never reaches PyPI.
- Existing PyPI files are never overwritten or silently skipped.
- Concurrent publishing is serialized and an in-progress upload is not
  cancelled by a newer merge.
- The workflow cannot write repository contents or publish from pull-request
  code before it reaches master.

## 4. Log

- 2026-07-16 - Owner requested automatic PyPI delivery on every master merge.
- 2026-07-16 - Trusted Publishing, immutable post-release versioning, artifact
  verification, tests and operator runbook implemented in TASK-076.
- 2026-07-16 - Repository implementation verified with 311 tests and a clean
  wheel install; owner-side PyPI Trusted Publisher activation remains pending.

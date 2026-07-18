---
spec: SPEC-008
title: Auditable changelog and release-note visibility
status: done
kind: new_feature
created: 2026-07-17
owner: javier@javierleon.dev
depends_on: [SPEC-007]
supersedes: []
sources: [owner-directive-20260717-changelog-visibility]
acceptance_criteria:
  - "python scripts/changelog.py validate"
  - "pytest -q"
  - "ruff check ."
  - "mypy hornero"
---

# SPEC-008 - Auditable changelog and release-note visibility

## 1. Context

Hornero has a Keep a Changelog history and immutable PyPI post-releases, but
changes are entered manually and the package page does not expose the exact
delta behind each build. Contributors need a conflict-resistant way to record
changes during review, and users need release notes both in the repository and
on PyPI.

## 2. Requirements

1. User-visible pull requests carry a small, typed changelog fragment.
2. CI validates fragment names and content and requires a fragment unless an
   explicit policy exemption applies.
3. Contributors can deterministically preview all unreleased fragments.
4. Every PyPI build replaces a marked README block in its isolated checkout
   with fragments changed by that push and immutable source links.
5. Builds without fragments fall back to commit subjects so dependency and
   operational changes remain visible.
6. PyPI metadata exposes direct Changelog and Release notes project URLs.
7. Repository documentation explains fragment creation, consolidation,
   exemptions and CI-only README projection.
8. Rapid merges retain independent publication runs so every change delta is
   represented by an immutable PyPI version.

## 3. Safety invariants

- Release-note generation is offline and deterministic.
- The publish workflow never commits its generated README back to the repo.
- Source links use the exact built commit, not a mutable branch.
- Missing or malformed fragments fail before packaging.
- Trusted Publishing permissions and package gates remain unchanged.

## 4. Log

- 2026-07-17 - Owner requested improved changelog control and visibility in
  both the repository and PyPI.
- 2026-07-17 - Fragment validation, PR policy, CI projection, metadata links,
  contributor documentation and deterministic tests implemented in TASK-077.

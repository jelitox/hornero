# Changelog fragments

Every pull request with a user-visible change adds one small Markdown file:

    .changes/PR-OR-SLUG.CATEGORY.md

Valid categories are `added`, `changed`, `deprecated`, `removed`, `fixed`,
`security`, and `dependencies`. Write one concise change description; a leading
Markdown bullet is optional.

Examples:

    .changes/123.added.md
    .changes/runtime-timeout.fixed.md
    .changes/dependabot-ruff.dependencies.md

Run `python scripts/changelog.py validate` to validate the directory and
`python scripts/changelog.py preview` to render the unreleased notes. The PR
workflow requires a new fragment unless the PR carries the `skip-changelog`
label or was opened by Dependabot. Dependabot commit subjects remain visible in
the generated PyPI release summary even without a fragment.

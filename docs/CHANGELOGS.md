# Changelog and release-note workflow

Hornero keeps one human-curated product history while projecting the exact
delta of every immutable CI build into its PyPI description.

## Pull requests

Add one Markdown fragment under `.changes/` for every user-visible change. The
filename is `NAME.CATEGORY.md`; `NAME` can be the PR number or a stable slug.
Supported categories are:

- `added`
- `changed`
- `deprecated`
- `removed`
- `fixed`
- `security`
- `dependencies`

The file contains one concise description. Run:

```bash
python scripts/changelog.py validate
python scripts/changelog.py preview
```

The `Changelog policy` pull-request workflow validates every fragment and
requires a newly changed fragment. Apply `skip-changelog` only to internal
changes with no user-visible effect. Dependabot is exempt because it cannot add
repository files to its generated PRs; its commit title is still included in
the corresponding PyPI release summary.

## Repository changelog

`CHANGELOG.md` follows Keep a Changelog. Before beginning a stable release,
review `python scripts/changelog.py preview`, consolidate the relevant entries
under the new version heading, and remove the consumed fragment files in the
same release PR. The fragments remain reviewable repository documentation
until that consolidation happens.

## PyPI projection

Every master build computes its immutable `MAJOR.MINOR.PATCH.postN` version,
then replaces the marked `Latest changes` block in `README.md` inside the CI
checkout only. The generated block groups fragments changed by that push and
links to an immutable changelog revision and exact GitHub comparison. If a push
has no fragment, commit subjects provide a deterministic fallback.

The committed README stays generic and is never rewritten by the workflow.
Because the build uses the projected README as package metadata, PyPI displays
the correct notes for that distribution. `project.urls` also exposes direct
Changelog and Release notes links in the PyPI sidebar.

Publication runs do not share a cancelling concurrency group. Every master
merge therefore keeps its own immutable post-release and exact change summary,
even when several pull requests merge close together.

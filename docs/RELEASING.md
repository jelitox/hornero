# Publishing Hornero to PyPI

Hornero publishes a wheel and source distribution after every successful push
to master, including pull-request merges. The workflow is
.github/workflows/publish-pypi.yml.

Before building, CI projects the fragments changed by the push into the marked
release-notes block in the package README. This makes the exact post-release
delta visible on PyPI without modifying the committed README. See
`docs/CHANGELOGS.md` for fragment policy and stable-release consolidation.

## One-time PyPI configuration

In the hornero project on PyPI, open **Manage > Publishing**, add a GitHub
Trusted Publisher, and enter:

| Field | Value |
|---|---|
| PyPI project | hornero |
| GitHub owner | jelitox |
| Repository | hornero |
| Workflow | publish-pypi.yml |
| Environment | pypi |

Create a GitHub environment named pypi and restrict its deployment branches to
master. Do not add a PYPI_API_TOKEN: the publish job requests a short-lived
OIDC credential and has no repository write permission.

If the hornero name has not been registered on PyPI yet, create a pending
publisher from the account publishing page with the same values before merging
the workflow.

## Version model

The repository keeps a stable SemVer base such as 0.4.0. CI derives an
immutable PEP 440 post-release:

    <base>.post<workflow-run-number * 1000 + run-attempt>

For example, run 42 attempt 3 publishes 0.4.0.post42003. This makes every merge
and every retry unique because PyPI never permits replacing an uploaded file.
Bump the base version in pyproject.toml when beginning a new product release
line.

## Pipeline gates

The build job has read-only repository access and:

1. runs the full test, Ruff, and MyPy gates;
2. assigns the CI-only version;
3. builds the wheel and source distribution;
4. validates metadata with Twine;
5. installs the wheel in a clean virtual environment and runs the CLI;
6. projects build-specific release notes into the PyPI description;
7. uploads the distributions as a seven-day GitHub artifact.

Only the separate publish job receives id-token: write. It downloads the
validated artifact and publishes it using PyPI Trusted Publishing with default
PEP 740 attestations. Each run has a distinct immutable version, so concurrent
merges retain independent publication runs instead of cancelling pending
changes.

Use **Actions > Publish Python package to PyPI > Run workflow** to retry or
perform a controlled manual publication. A rerun receives a new post-release
version through github.run_attempt.

## Local distribution build

Reproduce the non-publishing half of the pipeline before opening a release PR:

```bash
source .venv/bin/activate
uv build
uv run --with twine twine check --strict dist/*
```

Then install the wheel into an isolated temporary environment and smoke-test
the packaged entry point. Do not commit `dist/`; local artifacts are ignored
and CI rebuilds them from the reviewed commit.

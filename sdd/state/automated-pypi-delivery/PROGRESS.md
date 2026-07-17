# Automated PyPI delivery - progress checkpoint

Updated: 2026-07-16
Authority: SPEC-007 and TASK-076

## Completed

- Master-triggered GitHub Actions workflow implemented.
- Build and publish jobs separated; only publish receives OIDC permission.
- Stable repository versions become immutable PEP 440 post-releases in CI.
- Workflow retries receive distinct versions through github.run_attempt.
- Tests, Ruff, MyPy, Twine metadata and installed-wheel smoke gates defined.
- External Actions pinned to resolved commits; Dependabot maintenance enabled.
- PyPI metadata and operator runbook added.
- Local gates: 311 tests, Ruff clean, MyPy clean, TOML/YAML syntax valid.
- Local wheel and sdist build succeeded; wheel installed and CLI executed in a
  clean Python 3.11 environment.
- Simulated CI version 0.4.0.post42003 produced a wheel and sdist that both
  passed Twine strict metadata validation.

## Activation pending

1. In PyPI, register the Trusted Publisher for project hornero:
   owner jelitox, repository hornero, workflow publish-pypi.yml, environment
   pypi.
2. Create/restrict the GitHub pypi environment to deployment branch master.
3. Merge the workflow into master.
4. Observe the first Publish Python package to PyPI run and confirm the new
   post-release on the PyPI project page.

No PYPI_API_TOKEN secret is required or expected.

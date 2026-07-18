"""Changelog fragment policy and PyPI release-note projection."""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "changelog.py"
CHANGELOG_WORKFLOW = ROOT / ".github" / "workflows" / "changelog.yml"
PUBLISH_WORKFLOW = ROOT / ".github" / "workflows" / "publish-pypi.yml"


def _run(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )


def _git(cwd: Path, *args: str) -> str:
    result = _run(cwd, "git", *args)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _init_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "master")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "user.email", "test@example.com")
    changes = repo / ".changes"
    changes.mkdir()
    (changes / "README.md").write_text("fragment instructions\n", encoding="utf-8")
    (repo / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    (repo / "README.md").write_text(
        "# Example\n\n"
        "<!-- pypi-release-notes:start -->\n"
        "## Latest changes\n\n"
        "See the changelog.\n"
        "<!-- pypi-release-notes:end -->\n",
        encoding="utf-8",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "chore: baseline")
    return repo, _git(repo, "rev-parse", "HEAD")


def test_validate_rejects_malformed_or_empty_fragments(tmp_path: Path) -> None:
    changes = tmp_path / ".changes"
    changes.mkdir()
    (changes / "README.md").write_text("instructions\n", encoding="utf-8")
    (changes / "feature.unknown.md").write_text("Visible change\n", encoding="utf-8")

    invalid_name = _run(tmp_path, sys.executable, str(SCRIPT), "validate")
    assert invalid_name.returncode == 1
    assert "expected NAME.CATEGORY.md" in invalid_name.stderr

    (changes / "feature.unknown.md").unlink()
    (changes / "feature.fixed.md").write_text("\n", encoding="utf-8")
    empty = _run(tmp_path, sys.executable, str(SCRIPT), "validate")
    assert empty.returncode == 1
    assert "fragment must not be empty" in empty.stderr


def test_validate_requires_fragment_changed_from_base(tmp_path: Path) -> None:
    repo, base = _init_repo(tmp_path)
    fragment = repo / ".changes" / "feature.added.md"
    fragment.write_text("Expose release notes on PyPI.\n", encoding="utf-8")
    _git(repo, "add", str(fragment))
    _git(repo, "commit", "-m", "feat: add release notes")

    valid = _run(
        repo,
        sys.executable,
        str(SCRIPT),
        "validate",
        "--base-ref",
        base,
        "--require-new",
    )
    assert valid.returncode == 0, valid.stderr
    assert "Validated 1 changelog fragment" in valid.stdout

    missing = _run(
        repo,
        sys.executable,
        str(SCRIPT),
        "validate",
        "--base-ref",
        "HEAD",
        "--require-new",
    )
    assert missing.returncode == 1
    assert "requires a new .changes/NAME.CATEGORY.md" in missing.stderr


def test_prepare_pypi_groups_fragments_and_uses_immutable_links(
    tmp_path: Path,
) -> None:
    repo, before = _init_repo(tmp_path)
    fragment = repo / ".changes" / "release-notes.added.md"
    fragment.write_text(
        "Show the exact release delta in package metadata.\n",
        encoding="utf-8",
    )
    _git(repo, "add", str(fragment))
    _git(repo, "commit", "-m", "feat: improve release notes")
    after = _git(repo, "rev-parse", "HEAD")

    result = _run(
        repo,
        sys.executable,
        str(SCRIPT),
        "prepare-pypi",
        "--version",
        "1.2.3.post4001",
        "--before",
        before,
        "--after",
        after,
        "--repository-url",
        "https://github.com/example/project",
        "--write",
    )
    assert result.returncode == 0, result.stderr
    rendered = (repo / "README.md").read_text(encoding="utf-8")
    assert "## What's new in 1.2.3.post4001" in rendered
    assert "### Added" in rendered
    assert "Show the exact release delta in package metadata." in rendered
    assert f"/blob/{after}/CHANGELOG.md" in rendered
    assert f"/compare/{before}...{after}" in rendered
    assert "See the changelog." not in rendered


def test_prepare_pypi_falls_back_to_commit_subjects(tmp_path: Path) -> None:
    repo, before = _init_repo(tmp_path)
    (repo / "dependency.txt").write_text("new version\n", encoding="utf-8")
    _git(repo, "add", "dependency.txt")
    _git(repo, "commit", "-m", "chore(deps): bump dependency to 2.0")

    result = _run(
        repo,
        sys.executable,
        str(SCRIPT),
        "prepare-pypi",
        "--version",
        "1.2.3.post5001",
        "--repository-url",
        "https://github.com/example/project",
        "--write",
    )
    assert result.returncode == 0, result.stderr
    rendered = (repo / "README.md").read_text(encoding="utf-8")
    assert "### Changed" in rendered
    assert "chore(deps): bump dependency to 2.0" in rendered
    assert f"/compare/{before}..." in rendered


def test_metadata_and_workflows_expose_and_enforce_changelog() -> None:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        urls = tomllib.load(handle)["project"]["urls"]
    assert urls["Changelog"].endswith("/blob/master/CHANGELOG.md")
    assert urls["Release notes"].endswith("/releases")

    policy_content = CHANGELOG_WORKFLOW.read_text(encoding="utf-8")
    policy = yaml.load(policy_content, Loader=yaml.BaseLoader)
    assert "pull_request" in policy["on"]
    assert policy["permissions"] == {"contents": "read"}
    assert "--require-new" in policy_content
    assert "skip-changelog" in policy_content

    publish_content = PUBLISH_WORKFLOW.read_text(encoding="utf-8")
    publish = yaml.load(publish_content, Loader=yaml.BaseLoader)
    assert "concurrency" not in publish
    checkout = publish["jobs"]["build"]["steps"][0]
    assert checkout["with"]["fetch-depth"] == "0"
    assert "scripts/changelog.py prepare-pypi" in publish_content
    assert publish_content.index("prepare-pypi") < publish_content.index(
        "Build wheel and source distribution"
    )

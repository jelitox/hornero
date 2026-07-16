"""Automated PyPI release workflow and immutable versioning."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]
VERSION_SCRIPT = ROOT / "scripts" / "ci_release_version.py"
WORKFLOW = ROOT / ".github" / "workflows" / "publish-pypi.yml"


def test_ci_version_is_unique_for_runs_and_retries(tmp_path: Path) -> None:
    project = tmp_path / "pyproject.toml"
    project.write_text(
        '[project]\nname = "example"\nversion = "1.2.3"\n\n[tool.demo]\n'
        'version = "keep-me"\n',
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(VERSION_SCRIPT),
            "--pyproject",
            str(project),
            "--run-number",
            "42",
            "--run-attempt",
            "3",
            "--write",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "1.2.3.post42003"
    content = project.read_text(encoding="utf-8")
    assert 'version = "1.2.3.post42003"' in content
    assert 'version = "keep-me"' in content


def test_ci_version_rejects_non_release_base(tmp_path: Path) -> None:
    project = tmp_path / "pyproject.toml"
    project.write_text(
        '[project]\nname = "example"\nversion = "1.2.3.post1"\n',
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(VERSION_SCRIPT),
            "--pyproject",
            str(project),
            "--run-number",
            "1",
            "--run-attempt",
            "1",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "stable MAJOR.MINOR.PATCH" in result.stderr


def test_publish_workflow_has_bounded_oidc_permissions() -> None:
    content = WORKFLOW.read_text(encoding="utf-8")
    workflow = yaml.load(content, Loader=yaml.BaseLoader)

    assert workflow["on"]["push"]["branches"] == ["master"]
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["jobs"]["build"].get("permissions") is None
    assert workflow["jobs"]["publish"]["permissions"] == {
        "contents": "read",
        "id-token": "write",
    }
    assert "environment" in workflow["jobs"]["publish"]
    assert "persist-credentials: false" in content
    assert "skip-existing" not in content

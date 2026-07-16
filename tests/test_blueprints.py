"""SPEC-005 F13 project factory and blueprint drift gates."""

import json
import subprocess

from hornero.cli import main


def test_new_creates_git_repo_hornero_stack_and_blueprint_lock(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    assert main([
        "new", "AcmeService", "--blueprint", "python-service",
        "--var", "description=Acme API", "--commit",
    ]) == 0
    root = tmp_path / "AcmeService"
    assert (root / ".git").is_dir()
    assert (root / ".hornero" / "project.json").is_file()
    assert (root / ".hornero" / "blueprint.lock").is_file()
    assert (root / "sdd" / "specs").is_dir()
    assert (root / "src" / "acmeservice" / "api.py").is_file()
    assert (root / "Dockerfile").is_file()
    assert (root / ".github" / "workflows" / "ci.yml").is_file()
    branch = subprocess.run(
        ["git", "-C", str(root), "branch", "--show-current"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert branch == "main"
    assert "created python-service project" in capsys.readouterr().out


def test_new_fullstack_composes_web_and_extra_components(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main([
        "new", "Portal", "--blueprint", "fullstack", "--no-git"
    ]) == 0
    root = tmp_path / "Portal"
    assert (root / "web" / "package.json").is_file()
    lock = json.loads(
        (root / ".hornero" / "blueprint.lock").read_text(encoding="utf-8")
    )
    assert lock["components"] == ["base", "python", "api", "web", "docker", "ci"]


def test_new_refuses_nonempty_destination_without_clobber(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    destination = tmp_path / "Existing"
    destination.mkdir()
    sentinel = destination / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    assert main(["new", "Existing"]) == 1
    assert sentinel.read_text(encoding="utf-8") == "keep"
    assert "destination is not empty" in capsys.readouterr().err


def test_blueprint_status_reports_modified_and_deleted(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["new", "Library", "--blueprint", "python-lib", "--no-git"]) == 0
    root = tmp_path / "Library"
    monkeypatch.chdir(root)
    assert main(["blueprint", "status"]) == 0
    assert "current" in capsys.readouterr().out
    (root / "README.md").write_text("local edit\n", encoding="utf-8")
    (root / ".editorconfig").unlink()
    assert main(["blueprint", "status", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["files"]["README.md"] == "modified"
    assert result["files"][".editorconfig"] == "deleted"


def test_blueprint_list_works_outside_project(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["blueprint", "list"]) == 0
    out = capsys.readouterr().out
    assert "python-lib" in out and "fullstack" in out

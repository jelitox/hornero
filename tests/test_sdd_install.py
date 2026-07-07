"""F2.5 gate: install produces managed set + skeleton, lock hashes verify,
re-run is idempotent (git diff empty)."""

import json
import subprocess

from hornero.cli import main
from hornero.sdd_toolkit.lock import load_lock, sha256_file
from hornero.sdd_toolkit.manifest import MANIFEST_NAME

MANIFEST = {
    "name": "sdd-toolkit",
    "version": "2026.07.0",
    "managed": [".claude/commands/*.md", ".claude/rules/*.md",
                "sdd/WORKFLOW.md", "sdd/templates/*.md"],
    "scaffold": ["sdd/proposals/", "sdd/specs/", "sdd/tasks/active/",
                 "sdd/tasks/completed/", "sdd/tasks/index/",
                 "sdd/decisions/", "sdd/reports/"],
}

TOOLKIT_FILES = {
    ".claude/commands/sdd-start.md": "# /sdd-start\nStart a task.\n",
    ".claude/commands/sdd-task.md": "# /sdd-task\nDecompose a spec.\n",
    ".claude/rules/python-development.md": "Use uv. Always venv.\n",
    "sdd/WORKFLOW.md": "# SDD Workflow v1\n",
    "sdd/templates/task.md": "# TASK-<NNN>\n",
}


def _upstream(tmp_path):
    up = tmp_path / "toolkit-upstream"
    for rel, content in TOOLKIT_FILES.items():
        p = up / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    (up / MANIFEST_NAME).write_text(json.dumps(MANIFEST), encoding="utf-8")
    return up


def _repo(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.chdir(repo)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@e.o"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "T"], check=True)
    return repo


def _porcelain(repo):
    return subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"],
        capture_output=True, text=True, check=True,
    ).stdout


def test_f2_5_gate_install_and_idempotent_rerun(tmp_path, monkeypatch):
    up = _upstream(tmp_path)
    repo = _repo(tmp_path, monkeypatch)
    assert main(["sdd", "install", "--from", str(up)]) == 0

    # managed set present
    for rel in TOOLKIT_FILES:
        assert (repo / rel).read_text(encoding="utf-8") == TOOLKIT_FILES[rel]
    # skeleton present
    for d in MANIFEST["scaffold"]:
        assert (repo / d / ".gitkeep").exists()
    # lock hashes verify against upstream AND installed copies
    lock = load_lock(repo)
    assert lock.toolkit_version == "2026.07.0"
    assert sorted(lock.files) == sorted(TOOLKIT_FILES)
    for rel, entry in lock.files.items():
        assert entry.upstream_hash == sha256_file(up / rel)
        assert entry.installed_hash == sha256_file(repo / rel)

    # idempotency: commit, re-run, git diff empty
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "install"], check=True)
    assert main(["sdd", "install", "--from", str(up)]) == 0
    assert _porcelain(repo) == ""


def test_adopts_existing_identical_and_modified(tmp_path, monkeypatch, capsys):
    up = _upstream(tmp_path)
    repo = _repo(tmp_path, monkeypatch)
    # pre-existing hand-copied files: one identical, one locally edited
    (repo / ".claude" / "commands").mkdir(parents=True)
    (repo / ".claude" / "commands" / "sdd-start.md").write_text(
        TOOLKIT_FILES[".claude/commands/sdd-start.md"], encoding="utf-8"
    )
    (repo / ".claude" / "commands" / "sdd-task.md").write_text(
        "# /sdd-task\nLOCAL TWEAK.\n", encoding="utf-8"
    )
    assert main(["sdd", "install", "--from", str(up)]) == 0
    out = capsys.readouterr().out
    assert "1 adopted" in out and "1 kept as locally modified" in out
    # the local tweak survived
    assert "LOCAL TWEAK" in (repo / ".claude" / "commands" / "sdd-task.md").read_text()
    lock = load_lock(repo)
    entry = lock.files[".claude/commands/sdd-task.md"]
    assert entry.installed_hash != entry.upstream_hash  # reads as modified


def test_force_overwrites(tmp_path, monkeypatch):
    up = _upstream(tmp_path)
    repo = _repo(tmp_path, monkeypatch)
    (repo / "sdd").mkdir()
    (repo / "sdd" / "WORKFLOW.md").write_text("LOCAL\n", encoding="utf-8")
    assert main(["sdd", "install", "--from", str(up), "--force"]) == 0
    assert (repo / "sdd" / "WORKFLOW.md").read_text() == "# SDD Workflow v1\n"


def test_no_upstream_configured_refuses(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path, monkeypatch)
    assert main(["sdd", "install"]) == 2
    assert "no toolkit upstream configured" in capsys.readouterr().err
    assert load_lock(repo) is None  # nothing written


def test_fallback_manifest_warns(tmp_path, monkeypatch, capsys):
    up = _upstream(tmp_path)
    (up / MANIFEST_NAME).unlink()
    _repo(tmp_path, monkeypatch)
    assert main(["sdd", "install", "--from", str(up)]) == 0
    assert "built-in fallback patterns" in capsys.readouterr().out

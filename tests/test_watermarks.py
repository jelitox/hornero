"""F6 gate: watermark store + content snapshots; a second `report`/`reindex`
on an unchanged committed repo says "already current" and leaves git clean."""

import subprocess

from hornero import watermarks
from hornero.cli import main

SPEC = """---
spec: SPEC-001
title: CSV export
status: done
kind: new_feature
created: 2026-07-01
sources: [sig-a]
supersedes: []
acceptance_criteria: []
---

# SPEC-001 — CSV export

Export usage as CSV from src/exporter.
"""


def _repo(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.chdir(repo)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@e.o"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "T"], check=True)
    assert main(["init"]) == 0
    (repo / "sdd" / "specs" / "SPEC-001-csv.md").write_text(SPEC, encoding="utf-8")
    return repo


def _commit_all(repo):
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "baseline"], check=True)


def _porcelain(repo):
    return subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"],
        capture_output=True, text=True, check=True,
    ).stdout


def test_f6_gate_double_run_noop(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path, monkeypatch)
    assert main(["reindex"]) == 0
    assert main(["report"]) == 0
    wm = watermarks.load(repo)
    assert "reindex" in wm and "reports" in wm
    assert wm["reports"]["content_hash"]
    _commit_all(repo)

    # unchanged repo: both runs are no-ops — no watermark churn, clean tree
    assert main(["reindex"]) == 0
    assert main(["report"]) == 0
    out = capsys.readouterr().out
    assert "knowledge index already current" in out
    assert "reports already current" in out
    assert _porcelain(repo) == ""
    assert watermarks.load(repo) == wm  # bytes untouched


def test_change_updates_watermark_and_head(tmp_path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)
    _commit_all(repo)
    assert main(["report"]) == 0
    _commit_all(repo)
    first = watermarks.get(repo, "reports")
    assert first is not None and first["git_head"] is not None
    # real content change => new snapshot, watermark rewritten
    (repo / "sdd" / "specs" / "SPEC-001-csv.md").write_text(
        SPEC.replace("status: done", "status: approved"), encoding="utf-8"
    )
    _commit_all(repo)
    assert main(["report"]) == 0
    second = watermarks.get(repo, "reports")
    assert second is not None
    assert second["content_hash"] != first["content_hash"]
    assert second["git_head"] != first["git_head"]


def test_snapshot_exclude_and_ordering(tmp_path):
    d = tmp_path / "t"
    (d / "sub").mkdir(parents=True)
    (d / "a.txt").write_text("A")
    (d / "sub" / "b.txt").write_text("B")
    base = watermarks.content_snapshot([d])
    (d / "manifest.json").write_text("{volatile}")
    assert watermarks.content_snapshot([d], frozenset({"manifest.json"})) == base
    assert watermarks.content_snapshot([d]) != base
    assert watermarks.content_snapshot([tmp_path / "missing"]) == (
        watermarks.content_snapshot([])
    )


def test_store_roundtrip_and_corrupt_file_tolerated(tmp_path):
    root = tmp_path
    (root / ".hornero").mkdir()
    assert watermarks.get(root, "wiki") is None
    watermarks.update(root, "wiki", {"git_head": "abc", "content_hash": "h"})
    entry = watermarks.get(root, "wiki")
    assert entry is not None and entry["git_head"] == "abc"
    (root / ".hornero" / "watermarks.json").write_text("{corrupt", encoding="utf-8")
    assert watermarks.load(root) == {}  # full-run semantics, never a crash

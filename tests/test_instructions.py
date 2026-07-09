"""SPEC-003 §8: instruction-file injection — idempotent, surrounding content
preserved, semantic staleness only."""

import subprocess

from hornero.cli import main
from hornero.instructions import SECTION, inject


def _git_clean(repo):
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "c"], check=True)
    return lambda: subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"],
        capture_output=True, text=True, check=True,
    ).stdout


def test_creates_agents_md_when_neither_exists(tmp_path):
    assert inject(tmp_path) == ["AGENTS.md"]
    text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert text == SECTION
    assert not (tmp_path / "CLAUDE.md").exists()


def test_appends_to_existing_claude_md_preserving_content(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# My repo\n\nRules here.\n")
    assert inject(tmp_path) == ["CLAUDE.md"]
    text = (tmp_path / "CLAUDE.md").read_text()
    assert text.startswith("# My repo\n\nRules here.\n")
    assert "## Hornero" in text
    assert not (tmp_path / "AGENTS.md").exists()  # top-level EXISTING only


def test_idempotent_rerun_leaves_git_diff_empty(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.chdir(repo)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@e"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "T"], check=True)
    assert main(["init"]) == 0  # init injects
    porcelain = _git_clean(repo)
    assert inject(repo) == []  # semantically current: zero writes
    assert main(["init"]) == 0
    assert porcelain() == ""


def test_formatting_variants_are_not_stale(tmp_path):
    reflowed = SECTION.replace("Start here:\n", "Start   here:\n")
    (tmp_path / "AGENTS.md").write_text("# Intro\n\n" + reflowed + "\n## After\n\nx\n")
    assert inject(tmp_path) == []  # whitespace never counts as stale


def test_semantically_stale_section_is_refreshed_in_place(tmp_path):
    stale = SECTION.replace("wiki/quickstart.md", "docs/OLD.md")
    (tmp_path / "AGENTS.md").write_text("# Intro\n\n" + stale + "\n## After\n\nkeep me\n")
    assert inject(tmp_path) == ["AGENTS.md"]
    text = (tmp_path / "AGENTS.md").read_text()
    assert "wiki/quickstart.md" in text and "docs/OLD.md" not in text
    assert text.startswith("# Intro\n") and "keep me" in text  # neighbors intact


def test_both_files_get_the_section(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# C\n")
    (tmp_path / "AGENTS.md").write_text("# A\n")
    assert sorted(inject(tmp_path)) == ["AGENTS.md", "CLAUDE.md"]

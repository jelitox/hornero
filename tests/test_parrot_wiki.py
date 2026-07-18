"""ai-parrot bridge and Codex integration gates (offline, temp-repo only)."""

import io
import json
import subprocess
from pathlib import Path

import pytest

from hornero.cli import main
from hornero.memory.knowledge import Hit, ParrotWikiKnowledge
from hornero.parrot_wiki import (
    AGENTS_BEGIN,
    GIT_HOOK_BEGIN,
    HOOK_COMMAND,
    SKILL_MD,
    build_codex_nudge,
    install_codex_integration,
    integration_status,
    run_codex_hook,
    uninstall_codex_integration,
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / ".git/hooks").mkdir(parents=True)
    return tmp_path


def _mark_built(repo: Path) -> None:
    storage = repo / ".parrot/wiki"
    storage.mkdir(parents=True, exist_ok=True)
    (storage / "wiki.db").write_bytes(b"sqlite")


def test_install_writes_codex_native_assets_and_preserves_user_files(repo):
    (repo / "AGENTS.md").write_text("# User rules\n", encoding="utf-8")
    (repo / ".codex").mkdir()
    (repo / ".codex/hooks.json").write_text(
        json.dumps({
            "description": "mine",
            "hooks": {"PreToolUse": [{
                "matcher": "Bash",
                "hooks": [{"type": "command", "command": "echo mine"}],
            }]},
        }),
        encoding="utf-8",
    )

    actions = install_codex_integration(repo)

    assert actions
    assert (repo / ".parrot/wiki.json").is_file()
    agents = (repo / "AGENTS.md").read_text(encoding="utf-8")
    assert agents.startswith("# User rules")
    assert AGENTS_BEGIN in agents and "$parrot-wiki" in agents
    hooks = json.loads((repo / ".codex/hooks.json").read_text(encoding="utf-8"))
    assert hooks["description"] == "mine"
    assert hooks["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == "echo mine"
    assert any(
        item["hooks"][0]["command"] == HOOK_COMMAND
        for item in hooks["hooks"]["PreToolUse"]
    )
    skill = repo / ".agents/skills/parrot-wiki/SKILL.md"
    assert skill.read_text(encoding="utf-8") == SKILL_MD
    assert (repo / ".agents/skills/parrot-wiki/agents/openai.yaml").is_file()
    hook = repo / ".git/hooks/post-commit"
    assert GIT_HOOK_BEGIN in hook.read_text(encoding="utf-8")
    assert hook.stat().st_mode & 0o111
    assert ".parrot/" in (repo / ".gitignore").read_text(encoding="utf-8")


def test_install_is_idempotent(repo):
    install_codex_integration(repo)
    paths = [
        repo / "AGENTS.md",
        repo / ".codex/hooks.json",
        repo / ".agents/skills/parrot-wiki/SKILL.md",
        repo / ".agents/skills/parrot-wiki/agents/openai.yaml",
        repo / ".git/hooks/post-commit",
        repo / ".gitignore",
    ]
    before = {path: path.read_bytes() for path in paths}
    install_codex_integration(repo)
    assert {path: path.read_bytes() for path in paths} == before


def test_invalid_hooks_json_aborts_without_clobbering(repo):
    (repo / ".codex").mkdir()
    path = repo / ".codex/hooks.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(RuntimeError, match="cannot parse"):
        install_codex_integration(repo)
    assert path.read_text(encoding="utf-8") == "{broken"


def test_uninstall_removes_only_managed_assets_and_keeps_plane(repo):
    (repo / "AGENTS.md").write_text("# Mine\n", encoding="utf-8")
    install_codex_integration(repo)
    _mark_built(repo)
    uninstall_codex_integration(repo)

    assert (repo / "AGENTS.md").read_text(encoding="utf-8").startswith("# Mine")
    assert AGENTS_BEGIN not in (repo / "AGENTS.md").read_text(encoding="utf-8")
    assert (repo / ".parrot/wiki.json").is_file()
    assert (repo / ".parrot/wiki/wiki.db").is_file()
    assert not (repo / ".agents/skills/parrot-wiki/SKILL.md").exists()
    assert not (repo / ".codex/hooks.json").exists()
    assert not (repo / ".git/hooks/post-commit").exists()


def test_status_distinguishes_install_tool_and_built_state(repo, monkeypatch):
    monkeypatch.setattr("hornero.parrot_wiki.toolkit_available", lambda: True)
    install_codex_integration(repo, git_hook=False)
    before = integration_status(repo)
    assert before["config"] and before["repository_skill"]
    assert before["wikitoolkit"] and not before["wiki_built"]
    _mark_built(repo)
    assert integration_status(repo)["wiki_built"] is True


def _payload(repo: Path, command: str) -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"cmd": command},
        "cwd": str(repo),
    }


def test_codex_hook_nudges_search_only_when_built_and_throttles(repo):
    install_codex_integration(repo, git_hook=False)
    assert build_codex_nudge(_payload(repo, "rg symbol src"), root=repo) is None
    _mark_built(repo)
    first = build_codex_nudge(_payload(repo, "rg symbol src"), root=repo, now=1000)
    assert first is not None and "systemMessage" in first
    assert "permissionDecision" not in first
    assert build_codex_nudge(
        _payload(repo, "rg other src"), root=repo, now=1001
    ) is None
    assert build_codex_nudge(
        _payload(repo, "pytest -q"), root=repo, now=1061
    ) is None


def test_codex_hook_handles_command_and_source_reads(repo):
    install_codex_integration(repo, git_hook=False)
    _mark_built(repo)
    payload = _payload(repo, "cat hornero/cli.py")
    payload["tool_input"] = {"command": "cat hornero/cli.py"}
    assert build_codex_nudge(payload, root=repo, now=2000) is not None


def test_codex_hook_runtime_is_fail_silent():
    output = io.StringIO()
    assert run_codex_hook(io.StringIO("{broken"), output) == 0
    assert output.getvalue() == ""


def test_cli_delegates_to_wikitoolkit_without_requiring_wiki_model(
    repo, monkeypatch
):
    monkeypatch.chdir(repo)
    seen: list[tuple[Path, list[str]]] = []

    def fake_run(root: Path, arguments: list[str]) -> int:
        seen.append((root, arguments))
        return 0

    monkeypatch.setattr("hornero.parrot_wiki.run_toolkit", fake_run)
    assert main([
        "wiki", "parrot", "query", "how does dispatch work", "--top-k", "3",
        "--json",
    ]) == 0
    assert seen == [(
        repo,
        [
            "query", "--top-k", "3", "--budget", "2400", "--json", "--",
            "how does dispatch work",
        ],
    )]


def test_cli_installs_codex_without_wiki_model(repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    assert main(["wiki", "codex", "install", "--no-git-hook"]) == 0
    assert (repo / ".codex/hooks.json").is_file()
    assert "trusted repository" in capsys.readouterr().out


def test_parrot_knowledge_adapter_maps_json_rows(repo, monkeypatch):
    monkeypatch.setattr("hornero.parrot_wiki.toolkit_available", lambda: True)
    monkeypatch.setattr("hornero.parrot_wiki.wiki_built", lambda root: True)
    monkeypatch.setattr(
        "hornero.parrot_wiki.query_rows",
        lambda root, question, limit: [{
            "concept_id": "module:dispatch",
            "node_id": "hornero/adapters/dispatch.py",
            "score": 0.9,
            "summary": "Dispatches approved build briefs.",
            "category": "module",
        }],
    )
    layer = ParrotWikiKnowledge(repo)
    assert layer.retrieve("dispatch", 1) == [
        Hit(
            "hornero/adapters/dispatch.py",
            0.9,
            "Dispatches approved build briefs.",
            "module",
        )
    ]


def test_generated_git_hook_runs_without_wikitoolkit(repo):
    install_codex_integration(repo)
    proc = subprocess.run(
        [str(repo / ".git/hooks/post-commit")],
        cwd=repo,
        check=False,
    )
    assert proc.returncode == 0

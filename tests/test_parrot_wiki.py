"""ai-parrot bridge and coding-agent integration gates (offline only)."""

import io
import json
import subprocess
from pathlib import Path

import pytest

from hornero.cli import main
from hornero.memory.knowledge import Hit, ParrotWikiKnowledge
from hornero.parrot_wiki import (
    AGENTS_BEGIN,
    CLAUDE_BEGIN,
    CLAUDE_HOOK_COMMAND,
    GEMINI_BEGIN,
    GEMINI_HOOK_COMMAND,
    GIT_HOOK_BEGIN,
    HOOK_COMMAND,
    SKILL_MD,
    build_claude_nudge,
    build_codex_nudge,
    build_gemini_nudge,
    claude_integration_status,
    gemini_integration_status,
    install_claude_integration,
    install_codex_integration,
    install_gemini_integration,
    integration_status,
    run_codex_hook,
    run_gemini_hook,
    uninstall_claude_integration,
    uninstall_codex_integration,
    uninstall_gemini_integration,
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


@pytest.mark.parametrize(
    ("arguments", "forwarded"),
    [
        (
            [
                "remember", "Use signed contracts", "--title", "Contracts",
                "--category", "decision", "--link", "module:dispatch",
                "--rel", "governs", "--source", "SPEC-001", "--by", "codex",
                "--extract", "--json",
            ],
            [
                "remember", "--title", "Contracts", "--category", "decision",
                "--link", "module:dispatch", "--rel", "governs", "--source",
                "SPEC-001", "--by", "codex", "--extract", "--json", "--",
                "Use signed contracts",
            ],
        ),
        (
            ["note", "module:dispatch", "Verified", "--by", "claude", "--json"],
            [
                "note", "--by", "claude", "--json", "--", "module:dispatch",
                "Verified",
            ],
        ),
        (
            [
                "link", "module:dispatch", "spec:001", "--rel", "implements",
                "--by", "gemini", "--json",
            ],
            [
                "link", "--rel", "implements", "--by", "gemini", "--json",
                "--", "module:dispatch", "spec:001",
            ],
        ),
        (
            ["memories", "--category", "decision", "--limit", "7", "--json"],
            [
                "memories", "--limit", "7", "--category", "decision", "--json",
            ],
        ),
        (["audit", "--limit", "9", "--json"], ["audit", "--limit", "9", "--json"]),
        (
            ["ground", "dispatch requires approval", "--json"],
            ["ground", "--json", "--", "dispatch requires approval"],
        ),
    ],
)
def test_cli_delegates_parrot_authoring_commands(
    repo, monkeypatch, arguments, forwarded
):
    monkeypatch.chdir(repo)
    seen: list[tuple[Path, list[str]]] = []
    monkeypatch.setattr(
        "hornero.parrot_wiki.run_toolkit",
        lambda root, argv: seen.append((root, argv)) or 0,
    )

    assert main(["wiki", "parrot", *arguments]) == 0
    assert seen == [(repo, forwarded)]


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


def test_install_migrates_legacy_git_hook_marker(repo):
    hook = repo / ".git/hooks/post-commit"
    hook.write_text(
        "#!/bin/sh\n"
        "echo user\n"
        "# >>> parrot-wiki codex post-commit >>>\n"
        "old command\n"
        "# <<< parrot-wiki codex post-commit <<<\n",
        encoding="utf-8",
    )

    actions = install_codex_integration(repo)
    content = hook.read_text(encoding="utf-8")

    assert any("migrated" in action for action in actions)
    assert "echo user" in content
    assert "old command" not in content
    assert content.count(GIT_HOOK_BEGIN) == 1


def test_claude_install_preserves_settings_and_writes_native_assets(repo):
    (repo / "CLAUDE.md").write_text("# Mine\n", encoding="utf-8")
    (repo / ".claude").mkdir()
    (repo / ".claude/settings.json").write_text(
        json.dumps({"permissions": {"deny": ["Read(.env)"]}}), encoding="utf-8"
    )

    first = install_claude_integration(repo)
    before = {
        path: path.read_bytes()
        for path in (
            repo / "CLAUDE.md",
            repo / ".claude/settings.json",
            repo / ".claude/skills/parrot-wiki/SKILL.md",
            repo / ".git/hooks/post-commit",
        )
    }
    second = install_claude_integration(repo)

    assert first and second
    assert {path: path.read_bytes() for path in before} == before
    assert (repo / "CLAUDE.md").read_text(encoding="utf-8").startswith("# Mine")
    assert CLAUDE_BEGIN in (repo / "CLAUDE.md").read_text(encoding="utf-8")
    settings = json.loads(
        (repo / ".claude/settings.json").read_text(encoding="utf-8")
    )
    assert settings["permissions"]["deny"] == ["Read(.env)"]
    assert settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"] \
        == CLAUDE_HOOK_COMMAND
    assert (repo / ".claude/skills/parrot-wiki/SKILL.md").read_text(
        encoding="utf-8"
    ) == SKILL_MD
    assert claude_integration_status(repo)["project_skill"] is True


def test_claude_hook_uses_official_additional_context_contract(repo):
    install_claude_integration(repo, git_hook=False)
    _mark_built(repo)
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Grep",
        "tool_input": {"pattern": "dispatch"},
        "cwd": str(repo),
    }
    response = build_claude_nudge(payload, root=repo, now=2000)
    assert response == {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": response["hookSpecificOutput"]["additionalContext"],
        },
        "suppressOutput": True,
    }


def test_gemini_install_preserves_settings_and_writes_native_assets(repo):
    (repo / "GEMINI.md").write_text("# Mine\n", encoding="utf-8")
    (repo / ".gemini").mkdir()
    (repo / ".gemini/settings.json").write_text(
        json.dumps({"general": {"vimMode": True}}), encoding="utf-8"
    )

    install_gemini_integration(repo)
    install_gemini_integration(repo)

    guidance = (repo / "GEMINI.md").read_text(encoding="utf-8")
    assert guidance.startswith("# Mine") and guidance.count(GEMINI_BEGIN) == 1
    settings = json.loads(
        (repo / ".gemini/settings.json").read_text(encoding="utf-8")
    )
    assert settings["general"]["vimMode"] is True
    hook = settings["hooks"]["AfterTool"][0]
    assert hook["hooks"][0]["command"] == GEMINI_HOOK_COMMAND
    assert hook["hooks"][0]["timeout"] == 10_000
    assert (repo / ".gemini/skills/parrot-wiki/SKILL.md").read_text(
        encoding="utf-8"
    ) == SKILL_MD
    assert gemini_integration_status(repo)["after_tool_hook"] is True


@pytest.mark.parametrize(
    ("tool_name", "tool_input"),
    [
        ("grep_search", {"pattern": "dispatch"}),
        ("read_file", {"file_path": "hornero/cli.py"}),
        ("read_many_files", {"include": ["hornero/**/*.py"]}),
        ("run_shell_command", {"command": "rg dispatch hornero"}),
    ],
)
def test_gemini_hook_injects_context_after_source_tools(
    repo, tool_name, tool_input
):
    install_gemini_integration(repo, git_hook=False)
    _mark_built(repo)
    response = build_gemini_nudge(
        {
            "hook_event_name": "AfterTool",
            "tool_name": tool_name,
            "tool_input": tool_input,
            "cwd": str(repo),
        },
        root=repo,
        now=0,
    )
    assert response is not None
    assert response["hookSpecificOutput"]["hookEventName"] == "AfterTool"
    assert "additionalContext" in response["hookSpecificOutput"]
    assert "decision" not in response


def test_gemini_hook_runtime_is_fail_silent():
    output = io.StringIO()
    assert run_gemini_hook(io.StringIO("{broken"), output) == 0
    assert output.getvalue() == ""


def test_agent_uninstalls_keep_shared_git_hook_until_last_integration(repo):
    install_codex_integration(repo)
    install_claude_integration(repo)
    install_gemini_integration(repo)
    assert (repo / ".git/hooks/post-commit").read_text(encoding="utf-8").count(
        GIT_HOOK_BEGIN
    ) == 1

    uninstall_codex_integration(repo)
    uninstall_claude_integration(repo)
    assert (repo / ".git/hooks/post-commit").is_file()
    uninstall_gemini_integration(repo)
    assert not (repo / ".git/hooks/post-commit").exists()


@pytest.mark.parametrize("platform", ["claude", "gemini"])
def test_cli_installs_additional_agent_integrations(repo, monkeypatch, platform):
    monkeypatch.chdir(repo)
    assert main(["wiki", platform, "install", "--no-git-hook"]) == 0
    assert (repo / f".{platform}/skills/parrot-wiki/SKILL.md").is_file()

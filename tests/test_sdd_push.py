"""F4.5 gate: a mock runner receives branch + PR payload with the expected
files; nothing ever targets the default branch; the workspace loop touches
only repos carrying ``.hornero/sdd.lock``. No real ``gh``/network, ever."""

import json
from pathlib import Path

import pytest

from hornero.cli import main
from hornero.sdd_toolkit.cli_sync import SyncError
from hornero.sdd_toolkit.push import (
    DEFAULT_BRANCHES,
    RunResult,
    cmd_workspace,
    push,
    scan_secrets,
)

MANIFEST = {
    "name": "sdd-toolkit",
    "version": "2026.07.1",
    "managed": [".claude/commands/*.md"],
    "scaffold": [],
}

D = ".claude/commands"
REL = f"{D}/sdd-start.md"


class RecordingRunner:
    def __init__(self, fail_prefix: list[str] | None = None):
        self.calls: list[tuple[list[str], Path]] = []
        self.fail_prefix = fail_prefix

    def __call__(self, cmd: list[str], cwd: Path) -> RunResult:
        self.calls.append((cmd, cwd))
        if self.fail_prefix and cmd[: len(self.fail_prefix)] == self.fail_prefix:
            return RunResult(1, "", "boom")
        return RunResult(0, "https://example.invalid/pr/7", "")


def _write(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _upstream(tmp_path, name="toolkit-upstream"):
    up = tmp_path / name
    _write(up, REL, "# /sdd-start v1\n")
    _write(up, f"{D}/other.md", "# other\n")
    _write(up, "sdd-toolkit.manifest.json", json.dumps(MANIFEST))
    return up


@pytest.fixture
def env(tmp_path, monkeypatch):
    up = _upstream(tmp_path)
    repo = tmp_path / "acme-api"
    repo.mkdir()
    monkeypatch.chdir(repo)
    assert main(["sdd", "install", "--from", str(up)]) == 0
    # hand-improve one managed file => state modified (push candidate)
    _write(repo, REL, "# /sdd-start v1 + local improvement\n")
    return up, repo


def test_f4_5_gate_push_branch_and_pr_payload(env, capsys):
    up, repo = env
    runner = RecordingRunner()
    rc = push(repo, [REL], source=str(up), ref="main", runner=runner)
    assert rc == 0
    cmds = [c for c, _ in runner.calls]
    branch = "sdd-toolkit/promote-acme-api"
    title = f"sdd-toolkit: promote {REL} from acme-api"
    assert cmds[0] == ["git", "checkout", "-B", branch]
    assert cmds[1] == ["git", "add", REL]
    assert cmds[2] == ["git", "commit", "-m", title]
    assert cmds[3] == ["git", "push", "-u", "origin", branch]
    assert cmds[4][:4] == ["gh", "pr", "create", "--title"]
    assert cmds[4][4] == title and REL in cmds[4][6]  # --body lists the file
    # every step ran in the upstream checkout, never in the repo
    assert {cwd for _, cwd in runner.calls} == {up.resolve()}
    # nothing targets the default branch — the branch is namespaced
    for cmd in cmds:
        if cmd[:2] == ["git", "push"]:
            assert cmd[-1] == branch and cmd[-1] not in DEFAULT_BRANCHES
    # the improved bytes were copied into the upstream checkout
    assert (up / REL).read_text() == "# /sdd-start v1 + local improvement\n"
    assert "https://example.invalid/pr/7" in capsys.readouterr().out


def test_push_rejects_non_modified(env, capsys):
    up, repo = env
    runner = RecordingRunner()
    # other.md is current, nonsense.md is not managed: both refused, and
    # NOTHING was executed or copied
    rc = push(
        repo, [f"{D}/other.md", "nonsense.md"],
        source=str(up), ref="main", runner=runner,
    )
    assert rc == 1 and runner.calls == []
    out = capsys.readouterr().out
    assert "current" in out and "not managed" in out


def test_push_without_files_is_refused_listing_candidates(env):
    up, repo = env
    with pytest.raises(SyncError, match=REL):  # R8: explicit, per-file
        push(repo, [], source=str(up), ref="main", runner=RecordingRunner())


def test_secret_scan_refuses_and_override(env, capsys):
    up, repo = env
    token = "ghp_" + "a1B2" * 6
    _write(repo, REL, f"# improved\nexport GH_TOKEN={token}\n")
    runner = RecordingRunner()
    rc = push(repo, [REL], source=str(up), ref="main", runner=runner)
    assert rc == 1 and runner.calls == []  # refused, nothing executed
    assert "GitHub token" in capsys.readouterr().out
    rc = push(
        repo, [REL], source=str(up), ref="main", runner=runner,
        allow_secrets=True,
    )
    assert rc == 0 and runner.calls  # override is per-run
    assert "overridden" in capsys.readouterr().out


def test_scan_secrets_patterns():
    assert scan_secrets("AKIA" + "A" * 16) == ["AWS access key"]
    assert scan_secrets("-----BEGIN RSA PRIVATE KEY-----") == ["private key block"]
    assert scan_secrets("https://user:hunter2@host/x") == ["URL with userinfo"]
    assert scan_secrets("Bearer " + "t" * 24) == ["bearer token"]
    assert scan_secrets("plain prose, no tokens") == []


def test_push_failing_step_aborts(env, capsys):
    up, repo = env
    runner = RecordingRunner(fail_prefix=["git", "push"])
    rc = push(repo, [REL], source=str(up), ref="main", runner=runner)
    assert rc == 1
    assert not any(c[0] == "gh" for c, _ in runner.calls)  # never reached PR
    assert "push failed at" in capsys.readouterr().out


def test_cli_push_wiring(env, monkeypatch, capsys):
    up, repo = env
    import hornero.sdd_toolkit.push as push_mod

    runner = RecordingRunner()
    monkeypatch.setattr(push_mod, "subprocess_runner", runner)
    assert main(["sdd", "sync", "--push", REL]) == 0
    assert any(c[0] == "gh" for c, _ in runner.calls)


def test_workspace_fanout_only_lockfile_repos(tmp_path, monkeypatch, capsys):
    up = _upstream(tmp_path)
    ws = tmp_path / "workspace"
    ws.mkdir()
    # child with a lockfile, one file behind
    child = ws / "repo-a"
    child.mkdir()
    monkeypatch.chdir(child)
    assert main(["sdd", "install", "--from", str(up)]) == 0
    _write(up, REL, "# /sdd-start v2\n")
    # sibling WITHOUT a lockfile must not be touched
    sibling = ws / "repo-b"
    _write(sibling, REL, "untouched")
    (ws / "loose-file.txt").write_text("not a repo", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    rc = cmd_workspace(ws, synced_at="2026-07-08T00:00:00+00:00")
    assert rc == 0
    assert (child / REL).read_text() == "# /sdd-start v2\n"  # fast-forwarded
    assert (sibling / REL).read_text() == "untouched"
    out = capsys.readouterr().out
    assert "1 repo(s) synced" in out and "1 skipped" in out


def test_workspace_cli_and_diverged_child_propagates_rc(tmp_path, monkeypatch, capsys):
    up = _upstream(tmp_path)
    ws = tmp_path / "workspace"
    ws.mkdir()
    child = ws / "repo-a"
    child.mkdir()
    monkeypatch.chdir(child)
    assert main(["sdd", "install", "--from", str(up)]) == 0
    _write(up, REL, "# upstream moved\n")
    _write(child, REL, "# local moved too\n")  # => diverged
    monkeypatch.chdir(tmp_path)
    assert main(["sdd", "sync", "--workspace", str(ws)]) != 0  # blocks
    assert "DIVERGED" in capsys.readouterr().out

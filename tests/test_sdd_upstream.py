"""Upstream fetcher: local dirs, git clones, offline degradation."""

import subprocess

import pytest

from hornero.sdd_toolkit.upstream import CACHE_SUBDIR, UpstreamError, fetch_upstream

_GIT_ENV_ARGS = [
    "-c", "user.email=t@example.org", "-c", "user.name=T",
]


def _make_git_upstream(path):
    path.mkdir(parents=True, exist_ok=True)
    (path / "WORKFLOW.md").write_text("wf v1", encoding="utf-8")
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    subprocess.run(
        ["git", "-C", str(path), *_GIT_ENV_ARGS, "add", "-A"], check=True
    )
    subprocess.run(
        ["git", "-C", str(path), *_GIT_ENV_ARGS, "commit", "-qm", "v1"], check=True
    )
    return path


def test_local_plain_dir_source(tmp_path):
    src = tmp_path / "up"
    src.mkdir()
    (src / "f.md").write_text("x")
    out = fetch_upstream(str(src), "main", tmp_path / "repo")
    assert out.root == src.resolve()
    assert out.commit is None and out.refreshed is True


def test_local_git_repo_source_has_commit(tmp_path):
    src = _make_git_upstream(tmp_path / "up")
    out = fetch_upstream(str(src), "main", tmp_path / "repo")
    assert out.commit and len(out.commit) == 40


def test_url_clone_into_cache_and_refresh(tmp_path):
    src = _make_git_upstream(tmp_path / "up")
    repo = tmp_path / "repo"
    repo.mkdir()
    # file:// URL forces the clone path (a path string would be used in place)
    url = f"file://{src}"
    first = fetch_upstream(url, "main", repo)
    assert first.root == repo / CACHE_SUBDIR
    assert (first.root / "WORKFLOW.md").read_text() == "wf v1"
    # upstream moves forward; re-fetch refreshes the cache
    (src / "WORKFLOW.md").write_text("wf v2", encoding="utf-8")
    subprocess.run(["git", "-C", str(src), *_GIT_ENV_ARGS, "commit", "-qam", "v2"],
                   check=True)
    second = fetch_upstream(url, "main", repo)
    assert second.refreshed is True
    assert (second.root / "WORKFLOW.md").read_text() == "wf v2"
    assert second.commit != first.commit


def test_offline_with_cache_warns_not_raises(tmp_path):
    src = _make_git_upstream(tmp_path / "up")
    repo = tmp_path / "repo"
    repo.mkdir()
    fetch_upstream(f"file://{src}", "main", repo)
    # "network" gone: remote path deleted
    subprocess.run(["rm", "-rf", str(src)], check=True)
    out = fetch_upstream(f"file://{src}", "main", repo)
    assert out.refreshed is False
    assert (out.root / "WORKFLOW.md").read_text() == "wf v1"  # stale cache


def test_offline_without_cache_raises(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    with pytest.raises(UpstreamError, match="no cache exists"):
        fetch_upstream("file:///nonexistent/toolkit.git", "main", repo)
    assert not (repo / CACHE_SUBDIR).exists()  # no half clone left behind

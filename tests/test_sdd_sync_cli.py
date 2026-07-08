"""F3.5 gate: the six-state fixture matrix resolves per the §6 table via
``hornero sdd sync``; a diverged file blocks with exit code != 0; --dry-run
leaves ``git status --porcelain`` unchanged."""

import json
import subprocess

from hornero.cli import main
from hornero.sdd_toolkit.lock import load_lock, sha256_file

MANIFEST = {
    "name": "sdd-toolkit",
    "version": "2026.07.1",
    "managed": [".claude/commands/*.md"],
    "scaffold": [],
}

D = ".claude/commands"


def _write(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _upstream(tmp_path, files):
    up = tmp_path / "toolkit-upstream"
    for rel, content in files.items():
        _write(up, rel, content)
    _write(up, "sdd-toolkit.manifest.json", json.dumps(MANIFEST))
    return up


def _git_repo(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.chdir(repo)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@e.o"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "T"], check=True)
    return repo


def _commit_all(repo):
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-qm", "baseline"], check=True
    )


def _porcelain(repo):
    return subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"],
        capture_output=True, text=True, check=True,
    ).stdout


def _matrix(tmp_path, monkeypatch):
    """Install against V1 upstream, then sculpt all six §6 states."""
    up = _upstream(tmp_path, {
        f"{D}/current.md": "A",
        f"{D}/behind.md": "B1",
        f"{D}/modified.md": "M1",
        f"{D}/diverged.md": "D1",
        f"{D}/deleted.md": "X1",
        f"{D}/held.md": "H1",
    })
    repo = _git_repo(tmp_path, monkeypatch)
    assert main(["sdd", "install", "--from", str(up)]) == 0
    # upstream moves: behind, diverged, held get new versions; new.md appears
    _write(up, f"{D}/behind.md", "B2")
    _write(up, f"{D}/diverged.md", "D2")
    _write(up, f"{D}/held.md", "H2")
    _write(up, f"{D}/new.md", "N1")
    # local moves: modified + diverged edited, deleted removed, held on hold
    _write(repo, f"{D}/modified.md", "M-local")
    _write(repo, f"{D}/diverged.md", "D-local")
    (repo / D / "deleted.md").unlink()
    assert main(["sdd", "hold", f"{D}/held.md"]) == 0
    return up, repo


def test_status_one_line_per_file(tmp_path, monkeypatch, capsys):
    up, repo = _matrix(tmp_path, monkeypatch)
    assert main(["sdd", "status"]) == 0  # status reports drift, exit 0
    out = capsys.readouterr().out.splitlines()
    lines = {li.split()[1]: li.split()[0] for li in out if li.startswith((
        "current", "behind", "modified", "diverged", "deleted", "new", "held",
        "pinned",
    ))}
    assert lines == {
        f"{D}/current.md": "current",
        f"{D}/behind.md": "behind",
        f"{D}/modified.md": "modified",
        f"{D}/diverged.md": "diverged",
        f"{D}/deleted.md": "deleted_locally",
        f"{D}/new.md": "new_upstream",
        f"{D}/held.md": "held",
    }
    assert any(li.startswith("7 managed file(s):") for li in out)


def test_diff_renders_unified(tmp_path, monkeypatch, capsys):
    up, repo = _matrix(tmp_path, monkeypatch)
    assert main(["sdd", "diff", f"{D}/modified.md"]) == 0
    out = capsys.readouterr().out
    assert f"--- upstream/{D}/modified.md" in out
    assert f"+++ local/{D}/modified.md" in out
    assert "-M1" in out and "+M-local" in out
    # unknown file fails closed
    assert main(["sdd", "diff", "nope.md"]) == 2


def test_f3_5_gate_matrix_resolution_and_diverged_blocks(tmp_path, monkeypatch, capsys):
    up, repo = _matrix(tmp_path, monkeypatch)
    rc = main(["sdd", "sync", "--pull"])
    out = capsys.readouterr().out
    assert rc != 0  # diverged blocks
    assert f"{D}/diverged.md" in out
    # ...but the rest of the table resolved per §6:
    assert (repo / D / "behind.md").read_text() == "B2"       # fast-forward
    assert (repo / D / "new.md").read_text() == "N1"          # installed
    assert (repo / D / "modified.md").read_text() == "M-local"  # untouched
    assert (repo / D / "diverged.md").read_text() == "D-local"  # untouched
    assert (repo / D / "held.md").read_text() == "H1"         # policy held
    assert not (repo / D / "deleted.md").exists()             # needs --force
    lock = load_lock(repo)
    assert lock is not None
    assert lock.files[f"{D}/behind.md"].installed_hash == sha256_file(up / D / "behind.md")
    # force reinstalls the deleted file; diverged still blocks
    assert main(["sdd", "sync", "--force"]) != 0
    assert (repo / D / "deleted.md").read_text() == "X1"


def test_dry_run_touches_nothing(tmp_path, monkeypatch, capsys):
    up, repo = _matrix(tmp_path, monkeypatch)
    _commit_all(repo)
    rc = main(["sdd", "sync", "--dry-run"])
    assert rc != 0  # still signals the diverged file
    assert _porcelain(repo) == ""  # F2-style guarantee: zero writes
    out = capsys.readouterr().out
    assert "dry-run: nothing written" in out
    assert "would fast-forward" in out and "would install" in out


def test_theirs_ours_resolution(tmp_path, monkeypatch, capsys):
    up, repo = _matrix(tmp_path, monkeypatch)
    # --theirs: upstream wins, lock fast-forwarded
    assert main(["sdd", "sync", "--theirs", f"{D}/diverged.md"]) == 0
    assert (repo / D / "diverged.md").read_text() == "D2"
    lock = load_lock(repo)
    assert lock is not None
    entry = lock.files[f"{D}/diverged.md"]
    assert entry.installed_hash == entry.upstream_hash == sha256_file(
        up / D / "diverged.md"
    )
    # sculpt a fresh divergence, resolve --ours: local kept, re-baselined
    _write(up, f"{D}/diverged.md", "D3")
    _write(repo, f"{D}/diverged.md", "D-mine")
    assert main(["sdd", "sync", "--ours", f"{D}/diverged.md"]) == 0
    assert (repo / D / "diverged.md").read_text() == "D-mine"
    lock = load_lock(repo)
    assert lock is not None
    entry = lock.files[f"{D}/diverged.md"]
    assert entry.installed_hash == sha256_file(repo / D / "diverged.md")
    assert entry.upstream_hash == sha256_file(up / D / "diverged.md")
    # after --ours the file reads modified (push candidate), sync passes
    assert main(["sdd", "status"]) == 0
    assert f"modified         {D}/diverged.md" in capsys.readouterr().out
    # resolving a non-diverged file fails closed
    assert main(["sdd", "sync", "--theirs", f"{D}/current.md"]) == 2


def test_hold_pin_cli(tmp_path, monkeypatch, capsys):
    up, repo = _matrix(tmp_path, monkeypatch)
    assert main(["sdd", "pin", f"{D}/current.md"]) == 0
    lock = load_lock(repo)
    assert lock is not None
    assert lock.files[f"{D}/current.md"].policy == "pinned"
    assert lock.files[f"{D}/held.md"].policy == "local"
    # respected by sync: held.md never pulled even though upstream moved
    main(["sdd", "sync", "--theirs", f"{D}/diverged.md"])
    assert (repo / D / "held.md").read_text() == "H1"
    # unhold flips back to sync => next pull fast-forwards it
    assert main(["sdd", "unhold", f"{D}/held.md"]) == 0
    assert main(["sdd", "sync"]) == 0
    assert (repo / D / "held.md").read_text() == "H2"
    # unknown file fails closed
    assert main(["sdd", "hold", "nope.md"]) == 2


def test_sync_without_lock_fails_closed(tmp_path, monkeypatch, capsys):
    up = _upstream(tmp_path, {f"{D}/x.md": "X"})
    _git_repo(tmp_path, monkeypatch)
    assert main(["sdd", "status", "--from", str(up)]) == 2
    assert "sdd install" in capsys.readouterr().err


def test_sync_uses_lock_upstream_when_no_from(tmp_path, monkeypatch):
    # after install, status/sync need no --from: the lock carries the identity
    up, repo = _matrix(tmp_path, monkeypatch)
    lock = load_lock(repo)
    assert lock is not None and lock.upstream == str(up)
    assert main(["sdd", "status"]) == 0

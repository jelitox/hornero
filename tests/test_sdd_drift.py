"""Three-way drift engine (SPEC-002 §6): the full state matrix, and
``apply_pull`` performing exactly the table's actions — diverged bytes are
NEVER touched (CLAUDE.md invariant 4)."""

import hashlib

from hornero.sdd_toolkit.drift import DriftState, apply_pull, classify
from hornero.sdd_toolkit.lock import FileEntry, SddLock, load_lock
from hornero.sdd_toolkit.manifest import Manifest

MANIFEST = Manifest(
    name="sdd-toolkit", version="2026.07.0", managed=[".claude/commands/*.md"]
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _write(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _lock(files):
    return SddLock(
        upstream="up", upstream_ref="main", toolkit_version="2026.07.0",
        upstream_commit=None, synced_at="2026-07-07T00:00:00+00:00", files=files,
    )


def _entry(installed: str, upstream: str | None = None, policy: str = "sync"):
    return FileEntry(
        upstream_hash=_sha(upstream if upstream is not None else installed),
        installed_hash=_sha(installed),
        policy=policy,
    )


def _matrix(tmp_path):
    """One file per §6 state (+ held/pinned). Naming: <state>.md."""
    up, repo = tmp_path / "up", tmp_path / "repo"
    d = ".claude/commands"
    # upstream now (U)
    _write(up, f"{d}/current.md", "A")
    _write(up, f"{d}/behind.md", "B2")
    _write(up, f"{d}/modified.md", "M1")
    _write(up, f"{d}/diverged.md", "D2")
    _write(up, f"{d}/deleted.md", "X1")
    _write(up, f"{d}/new.md", "N1")
    _write(up, f"{d}/held.md", "H2")
    _write(up, f"{d}/pinned.md", "P2")
    # current on disk (C)
    _write(repo, f"{d}/current.md", "A")
    _write(repo, f"{d}/behind.md", "B1")
    _write(repo, f"{d}/modified.md", "M2")
    _write(repo, f"{d}/diverged.md", "D3")
    # deleted.md: missing locally
    # new.md: not in lock
    _write(repo, f"{d}/held.md", "H1")
    _write(repo, f"{d}/pinned.md", "P1")
    # last sync (L)
    lock = _lock({
        f"{d}/current.md": _entry("A"),
        f"{d}/behind.md": _entry("B1"),
        f"{d}/modified.md": _entry("M1"),
        f"{d}/diverged.md": _entry("D1"),
        f"{d}/deleted.md": _entry("X1"),
        f"{d}/held.md": _entry("H1", policy="local"),
        f"{d}/pinned.md": _entry("P1", policy="pinned"),
    })
    return up, repo, lock


def test_matrix_all_six_states(tmp_path):
    up, repo, lock = _matrix(tmp_path)
    drifts = {d.path.rsplit("/", 1)[-1]: d for d in classify(up, repo, MANIFEST, lock)}
    assert {n: d.state for n, d in drifts.items()} == {
        "current.md": DriftState.CURRENT,
        "behind.md": DriftState.BEHIND,
        "modified.md": DriftState.MODIFIED,
        "diverged.md": DriftState.DIVERGED,
        "deleted.md": DriftState.DELETED_LOCALLY,
        "new.md": DriftState.NEW_UPSTREAM,
        "held.md": DriftState.HELD,
        "pinned.md": DriftState.PINNED,
    }
    # results come back sorted by path, hashes carry all three legs
    assert [d.path for d in classify(up, repo, MANIFEST, lock)] == sorted(
        d.path for d in classify(up, repo, MANIFEST, lock)
    )
    assert drifts["deleted.md"].current_hash is None
    assert drifts["new.md"].installed_hash is None
    assert drifts["behind.md"].upstream_hash == _sha("B2")


def test_same_bytes_both_sides_is_behind_not_diverged(tmp_path):
    # U≠L and C≠L but C==U (user hand-copied the new version): nothing
    # conflicts — fast-forward only needs to refresh the lock.
    up, repo = tmp_path / "up", tmp_path / "repo"
    rel = ".claude/commands/copied.md"
    _write(up, rel, "V2")
    _write(repo, rel, "V2")
    lock = _lock({rel: _entry("V1")})
    (drift,) = classify(up, repo, MANIFEST, lock)
    assert drift.state is DriftState.BEHIND


def test_upstream_deletion_never_fast_forwards(tmp_path):
    # OQ9: file dropped upstream is outside the §6 matrix — an unmodified
    # local copy stays current (a deletion cannot be "copied"), an edited
    # one reads modified. Pull must not crash on either.
    up, repo = tmp_path / "up", tmp_path / "repo"
    up.mkdir()
    kept, edited = ".claude/commands/kept.md", ".claude/commands/edited.md"
    _write(repo, kept, "K1")
    _write(repo, edited, "E2")
    lock = _lock({kept: _entry("K1"), edited: _entry("E1")})
    drifts = {d.path: d.state for d in classify(up, repo, MANIFEST, lock)}
    assert drifts == {kept: DriftState.CURRENT, edited: DriftState.MODIFIED}
    report = apply_pull(classify(up, repo, MANIFEST, lock), up, repo, lock)
    assert report.pulled == [] and (repo / kept).read_text() == "K1"


def test_adopted_as_modified_never_reads_behind(tmp_path):
    # install() keeps a hand-modified file and locks it with a DIRTY baseline
    # (installed_hash = local, upstream_hash = upstream). It must classify
    # MODIFIED — a BEHIND reading would let the next pull clobber the very
    # file adoption kept.
    up, repo = tmp_path / "up", tmp_path / "repo"
    rel = ".claude/commands/adopted.md"
    _write(up, rel, "U0")
    _write(repo, rel, "my local flavor")
    lock = _lock({rel: FileEntry(
        upstream_hash=_sha("U0"), installed_hash=_sha("my local flavor"),
    )})
    (drift,) = classify(up, repo, MANIFEST, lock)
    assert drift.state is DriftState.MODIFIED
    report = apply_pull([drift], up, repo, lock)
    assert report.pulled == [] and (repo / rel).read_text() == "my local flavor"
    # upstream then moves over the dirty baseline: the human decides
    _write(up, rel, "U1")
    (drift,) = classify(up, repo, MANIFEST, lock)
    assert drift.state is DriftState.DIVERGED


def test_pull_fast_forwards_behind_and_new(tmp_path):
    up, repo, lock = _matrix(tmp_path)
    d = ".claude/commands"
    report = apply_pull(classify(up, repo, MANIFEST, lock), up, repo, lock)
    assert report.pulled == [f"{d}/behind.md"]
    assert report.installed == [f"{d}/new.md"]
    assert (repo / d / "behind.md").read_text() == "B2"
    assert (repo / d / "new.md").read_text() == "N1"
    # lock fast-forwarded AND persisted
    saved = load_lock(repo)
    assert saved is not None
    assert saved.files[f"{d}/behind.md"].installed_hash == _sha("B2")
    assert saved.files[f"{d}/new.md"].upstream_hash == _sha("N1")
    # re-classify: both are now current
    states = {x.path: x.state for x in classify(up, repo, MANIFEST, saved)}
    assert states[f"{d}/behind.md"] is DriftState.CURRENT
    assert states[f"{d}/new.md"] is DriftState.CURRENT


def test_pull_never_touches_diverged_or_modified(tmp_path):
    up, repo, lock = _matrix(tmp_path)
    d = ".claude/commands"
    report = apply_pull(classify(up, repo, MANIFEST, lock), up, repo, lock)
    assert report.diverged == [f"{d}/diverged.md"]
    assert (repo / d / "diverged.md").read_text() == "D3"  # bytes untouched
    assert (repo / d / "modified.md").read_text() == "M2"
    # lock legs for both files unchanged
    saved = load_lock(repo)
    assert saved is not None
    assert saved.files[f"{d}/diverged.md"] == lock.files[f"{d}/diverged.md"]
    assert saved.files[f"{d}/modified.md"] == lock.files[f"{d}/modified.md"]


def test_deleted_locally_requires_force(tmp_path):
    up, repo, lock = _matrix(tmp_path)
    d = ".claude/commands"
    report = apply_pull(classify(up, repo, MANIFEST, lock), up, repo, lock)
    assert report.deleted == [f"{d}/deleted.md"]
    assert not (repo / d / "deleted.md").exists()  # still absent
    report = apply_pull(
        classify(up, repo, MANIFEST, lock), up, repo, lock, force=True
    )
    assert report.reinstalled == [f"{d}/deleted.md"]
    assert (repo / d / "deleted.md").read_text() == "X1"


def test_policies_hold_and_pin(tmp_path):
    up, repo, lock = _matrix(tmp_path)
    d = ".claude/commands"
    report = apply_pull(
        classify(up, repo, MANIFEST, lock), up, repo, lock, force=True
    )
    # force is NOT a policy override: held/pinned are never copied over
    assert (repo / d / "held.md").read_text() == "H1"
    assert (repo / d / "pinned.md").read_text() == "P1"
    for rel in (f"{d}/held.md", f"{d}/pinned.md"):
        assert rel not in report.pulled + report.installed + report.reinstalled
    saved = load_lock(repo)
    assert saved is not None
    assert saved.files[f"{d}/held.md"].policy == "local"
    assert saved.files[f"{d}/pinned.md"].policy == "pinned"


def test_new_upstream_path_with_local_file_is_adopted_not_clobbered(tmp_path):
    # Adoption over clobbering (mirrors install): a local file sitting at a
    # path that is new upstream is kept and locked as modified.
    up, repo = tmp_path / "up", tmp_path / "repo"
    rel = ".claude/commands/new.md"
    _write(up, rel, "N1")
    _write(repo, rel, "my local version")
    lock = _lock({})
    report = apply_pull(classify(up, repo, MANIFEST, lock), up, repo, lock)
    assert report.kept == [rel] and report.installed == []
    assert (repo / rel).read_text() == "my local version"
    saved = load_lock(repo)
    assert saved is not None
    assert saved.files[rel].installed_hash == _sha("my local version")
    assert saved.files[rel].upstream_hash == _sha("N1")

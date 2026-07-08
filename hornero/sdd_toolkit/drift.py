"""Three-way drift engine (SPEC-002 §6).

Per managed file, compare three hashes — U (upstream now), L (lockfile
``installed_hash``, last sync), C (current file on disk) — into the §6
matrix. Hard rule (CLAUDE.md invariant 4): **diverged files are never
auto-resolved** — no timestamp heuristics, no "newest wins". ``apply_pull``
performs exactly the table's actions; rendering and ``--theirs``/``--ours``
resolution belong to the CLI layer (TASK-026), push to TASK-027.
"""

import shutil
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from hornero.sdd_toolkit.lock import FileEntry, SddLock, save_lock, sha256_file
from hornero.sdd_toolkit.manifest import Manifest, resolve_managed


class DriftState(StrEnum):
    CURRENT = "current"
    BEHIND = "behind"
    MODIFIED = "modified"
    DIVERGED = "diverged"
    DELETED_LOCALLY = "deleted_locally"
    NEW_UPSTREAM = "new_upstream"
    HELD = "held"      # policy=local: reported, never pulled
    PINNED = "pinned"  # policy=pinned: reported, never pulled


@dataclass
class FileDrift:
    path: str
    state: DriftState
    upstream_hash: str | None
    installed_hash: str | None
    current_hash: str | None


@dataclass
class PullReport:
    pulled: list[str] = field(default_factory=list)       # behind, fast-forwarded
    installed: list[str] = field(default_factory=list)    # new upstream
    reinstalled: list[str] = field(default_factory=list)  # deleted locally + force
    diverged: list[str] = field(default_factory=list)     # blocked, bytes untouched
    deleted: list[str] = field(default_factory=list)      # left absent (no --force)
    kept: list[str] = field(default_factory=list)         # new upstream, local file
    #                                            adopted as modified (no clobber)


def _hash_or_none(path: Path) -> str | None:
    return sha256_file(path) if path.is_file() else None


def classify(
    upstream_root: Path,
    repo_root: Path,
    manifest: Manifest,
    lock: SddLock,
) -> list[FileDrift]:
    """The §6 matrix over the union of upstream managed files and lock
    entries, sorted by path. Policy ``local``/``pinned`` wins over the hash
    comparison: those files are reported (HELD/PINNED) and never pulled.

    Both lock legs matter: "upstream moved" is U-live vs
    ``entry.upstream_hash``, "local moved" is C vs ``entry.installed_hash``.
    A file install() adopted as locally modified has a *dirty baseline*
    (installed != upstream at sync time) — it must read MODIFIED (push
    candidate), never BEHIND, or a pull would clobber the very file
    adoption kept. When upstream later moves over a dirty baseline the
    human decides: DIVERGED."""
    paths = sorted(set(resolve_managed(upstream_root, manifest)) | set(lock.files))
    drifts: list[FileDrift] = []
    for rel in paths:
        upstream = _hash_or_none(upstream_root / rel)
        current = _hash_or_none(repo_root / rel)
        entry = lock.files.get(rel)

        if entry is None:
            state = DriftState.NEW_UPSTREAM
        elif entry.policy == "local":
            state = DriftState.HELD
        elif entry.policy == "pinned":
            state = DriftState.PINNED
        elif current is None:
            state = DriftState.DELETED_LOCALLY
        elif upstream is None:
            # OQ9: upstream deletion is outside the §6 matrix — nothing to
            # copy, never delete locally.
            state = (
                DriftState.CURRENT
                if current == entry.installed_hash
                else DriftState.MODIFIED
            )
        elif current == upstream:
            # Disk already matches upstream-now; stale lock legs are a
            # fast-forward (copy is a no-op, the lock refreshes).
            state = (
                DriftState.CURRENT
                if entry.installed_hash == upstream and entry.upstream_hash == upstream
                else DriftState.BEHIND
            )
        elif upstream == entry.upstream_hash:
            # Upstream unmoved since sync; disk differs from it — locally
            # edited OR adopted-as-modified. Either way: push candidate.
            state = DriftState.MODIFIED
        elif (
            current == entry.installed_hash
            and entry.installed_hash == entry.upstream_hash
        ):
            state = DriftState.BEHIND  # clean baseline, only upstream moved
        else:
            state = DriftState.DIVERGED

        drifts.append(
            FileDrift(
                path=rel,
                state=state,
                upstream_hash=upstream,
                installed_hash=entry.installed_hash if entry else None,
                current_hash=current,
            )
        )
    return drifts


def _pull_file(upstream_root: Path, repo_root: Path, lock: SddLock, rel: str) -> None:
    src = upstream_root / rel
    dest = repo_root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    upstream_hash = sha256_file(src)
    policy = lock.files[rel].policy if rel in lock.files else "sync"
    lock.files[rel] = FileEntry(
        upstream_hash=upstream_hash, installed_hash=upstream_hash, policy=policy
    )


def apply_pull(
    drifts: list[FileDrift],
    upstream_root: Path,
    repo_root: Path,
    lock: SddLock,
    *,
    force: bool = False,
) -> PullReport:
    """Exactly the §6 table, pure filesystem, no prompting: BEHIND and
    NEW_UPSTREAM fast-forward (copy + lock), DELETED_LOCALLY reinstalls only
    with ``force``, DIVERGED is reported with its bytes untouched, and
    MODIFIED/CURRENT/HELD/PINNED are left alone. The lock is saved iff
    something changed."""
    report = PullReport()
    changed = False
    for drift in drifts:
        if drift.state is DriftState.BEHIND:
            _pull_file(upstream_root, repo_root, lock, drift.path)
            report.pulled.append(drift.path)
            changed = True
        elif drift.state is DriftState.NEW_UPSTREAM:
            if (
                drift.current_hash is not None
                and drift.current_hash != drift.upstream_hash
                and not force
            ):
                # Adoption over clobbering (mirrors install): an unmanaged
                # local file at a new upstream path is kept, locked as
                # modified — never silently overwritten.
                assert drift.upstream_hash is not None
                lock.files[drift.path] = FileEntry(
                    upstream_hash=drift.upstream_hash,
                    installed_hash=drift.current_hash,
                )
                report.kept.append(drift.path)
            else:
                _pull_file(upstream_root, repo_root, lock, drift.path)
                report.installed.append(drift.path)
            changed = True
        elif drift.state is DriftState.DELETED_LOCALLY:
            if force and drift.upstream_hash is not None:
                _pull_file(upstream_root, repo_root, lock, drift.path)
                report.reinstalled.append(drift.path)
                changed = True
            else:
                report.deleted.append(drift.path)
        elif drift.state is DriftState.DIVERGED:
            report.diverged.append(drift.path)
        # MODIFIED / CURRENT / HELD / PINNED: nothing, by design.
    if changed:
        save_lock(repo_root, lock)
    return report

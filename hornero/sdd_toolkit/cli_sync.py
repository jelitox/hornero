"""``hornero sdd status|diff|sync|hold|unhold|pin`` (SPEC-002 §7, F3.5).

Thin CLI over the drift engine — classification and pull mechanics live in
:mod:`hornero.sdd_toolkit.drift`. ``status`` reports and never fails on
drift; ``sync`` blocks (exit != 0) on any DIVERGED file lacking an explicit
``--theirs``/``--ours`` resolution — the human resolves, never a heuristic.
"""

import difflib
from collections.abc import Callable
from pathlib import Path

from hornero.paths import contained_path, validate_relative_path

from hornero.sdd_toolkit.drift import (
    DriftState,
    FileDrift,
    apply_pull,
    classify,
)
from hornero.sdd_toolkit.lock import (
    FileEntry,
    SddLock,
    load_lock,
    save_lock,
    set_policy,
    sha256_file,
)
from hornero.sdd_toolkit.manifest import Manifest, load_manifest
from hornero.sdd_toolkit.upstream import Checkout, fetch_upstream

Echo = Callable[[str], None]

_POLICY_BY_COMMAND = {"hold": "local", "unhold": "sync", "pin": "pinned"}


class SyncError(RuntimeError):
    """Preconditions for a sync-family command are not met."""


def _prep(
    root: Path, source: str, ref: str, echo: Echo
) -> tuple[Checkout, Manifest, SddLock, list[FileDrift]]:
    lock = load_lock(root)
    if lock is None:
        raise SyncError("no .hornero/sdd.lock — run 'hornero sdd install' first")
    checkout = fetch_upstream(source, ref, root)
    if not checkout.refreshed:
        echo("warning: upstream unreachable — comparing against a stale cache")
    manifest, from_fallback = load_manifest(checkout.root)
    if from_fallback:
        echo("warning: upstream has no manifest; using built-in fallback patterns")
    return checkout, manifest, lock, classify(checkout.root, root, manifest, lock)


def cmd_status(root: Path, source: str, ref: str, *, echo: Echo = print) -> int:
    """G4: the drift table, one line per managed file. Reports, never fails."""
    _, _, _, drifts = _prep(root, source, ref, echo)
    for d in drifts:
        echo(f"{d.state.value:<16} {d.path}")
    by_state: dict[str, int] = {}
    for d in drifts:
        by_state[d.state.value] = by_state.get(d.state.value, 0) + 1
    summary = ", ".join(f"{n} {s}" for s, n in sorted(by_state.items()))
    echo(f"{len(drifts)} managed file(s): {summary or 'none'}")
    return 0


def _read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines(keepends=True) if path.is_file() else []


def cmd_diff(
    root: Path, source: str, ref: str, file: str | None, *, echo: Echo = print
) -> int:
    checkout, _, _, drifts = _prep(root, source, ref, echo)
    if file is not None:
        targets = [d for d in drifts if d.path == file]
        if not targets:
            raise SyncError(f"{file!r} is not a managed file")
    else:
        targets = [d for d in drifts if d.state is not DriftState.CURRENT]
    for d in targets:
        diff = difflib.unified_diff(
            _read_lines(contained_path(checkout.root, d.path)),
            _read_lines(contained_path(root, d.path)),
            fromfile=f"upstream/{d.path}",
            tofile=f"local/{d.path}",
        )
        text = "".join(diff)
        if text:
            echo(text.rstrip("\n"))
    return 0


def _resolve_theirs(checkout: Checkout, root: Path, lock: SddLock, rel: str) -> None:
    rel = validate_relative_path(rel)
    src, dest = contained_path(checkout.root, rel), contained_path(root, rel)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(src.read_bytes())
    upstream_hash = sha256_file(src)
    lock.files[rel] = FileEntry(
        upstream_hash=upstream_hash,
        installed_hash=upstream_hash,
        policy=lock.files[rel].policy,
    )


def _resolve_ours(checkout: Checkout, root: Path, lock: SddLock, rel: str) -> None:
    # Keep local bytes; re-baseline BOTH legs against now (installed_hash =
    # current, upstream_hash = upstream-now) => the file reads MODIFIED (a
    # push candidate) and a further upstream move reads DIVERGED again.
    lock.files[rel] = FileEntry(
        upstream_hash=sha256_file(contained_path(checkout.root, rel)),
        installed_hash=sha256_file(contained_path(root, rel)),
        policy=lock.files[rel].policy,
    )


def cmd_sync(
    root: Path,
    source: str,
    ref: str,
    *,
    dry_run: bool = False,
    theirs: list[str] | None = None,
    ours: list[str] | None = None,
    force: bool = False,
    synced_at: str = "",
    echo: Echo = print,
) -> int:
    theirs, ours = list(theirs or []), list(ours or [])
    checkout, manifest, lock, drifts = _prep(root, source, ref, echo)

    overlap = set(theirs) & set(ours)
    if overlap:
        raise SyncError(f"--theirs and --ours overlap: {', '.join(sorted(overlap))}")
    diverged_paths = {d.path for d in drifts if d.state is DriftState.DIVERGED}
    for rel in [*theirs, *ours]:
        if rel not in {d.path for d in drifts}:
            raise SyncError(f"{rel!r} is not a managed file")
        if rel not in diverged_paths:
            raise SyncError(f"{rel!r} is not diverged — nothing to resolve")

    resolved = set(theirs) | set(ours)
    unresolved = sorted(diverged_paths - resolved)

    if dry_run:
        actions = {
            DriftState.BEHIND: "would fast-forward",
            DriftState.NEW_UPSTREAM: "would install",
            DriftState.DELETED_LOCALLY: (
                "would reinstall (--force)" if force else "deleted locally (needs --force)"
            ),
            DriftState.DIVERGED: "DIVERGED — needs --theirs/--ours",
        }
        for d in drifts:
            action = actions.get(d.state, "nothing")
            if d.path in theirs:
                action = "would resolve --theirs (copy upstream)"
            elif d.path in ours:
                action = "would resolve --ours (keep local, re-baseline lock)"
            echo(f"{d.state.value:<16} {d.path}: {action}")
        echo("dry-run: nothing written")
        if unresolved:
            echo(f"diverged, unresolved: {', '.join(unresolved)}")
            return 1
        return 0

    for rel in theirs:
        _resolve_theirs(checkout, root, lock, rel)
        echo(f"resolved --theirs: {rel}")
    for rel in ours:
        _resolve_ours(checkout, root, lock, rel)
        echo(f"resolved --ours: {rel} (kept local, lock re-baselined)")

    remaining = [d for d in drifts if d.path not in resolved]
    report = apply_pull(remaining, checkout.root, root, lock, force=force)

    # §7: a successful sync rewrites the lock's sync identity.
    lock.synced_at = synced_at
    lock.upstream_commit = checkout.commit
    lock.toolkit_version = manifest.version
    save_lock(root, lock)

    echo(
        f"sync: {len(report.pulled)} fast-forwarded, {len(report.installed)} "
        f"installed, {len(report.reinstalled)} reinstalled, {len(report.kept)} "
        f"kept, {len(theirs) + len(ours)} resolved"
    )
    for rel in report.deleted:
        echo(f"deleted locally (use --force to reinstall): {rel}")
    if unresolved:
        echo(f"DIVERGED — resolve with --theirs/--ours or merge by hand: "
             f"{', '.join(unresolved)}")
        return 1
    return 0


def cmd_policy(root: Path, file: str, command: str, *, echo: Echo = print) -> int:
    lock = load_lock(root)
    if lock is None:
        raise SyncError("no .hornero/sdd.lock — run 'hornero sdd install' first")
    policy = _POLICY_BY_COMMAND[command]
    try:
        set_policy(lock, file, policy)
    except ValueError as exc:
        raise SyncError(str(exc)) from exc
    save_lock(root, lock)
    echo(f"{file}: policy={policy}")
    return 0

"""``hornero sdd install`` (SPEC-002 G1, §7).

Toolkit files + state skeleton + lockfile in one pass. Adoption over
clobbering: a pre-existing file with the upstream's hash is adopted as
current; a hand-modified one is KEPT (the lock records its local hash, so
drift reads ``modified``) unless ``--force``. Idempotent: an unchanged
re-run rewrites nothing — including the lock, whose ``synced_at`` is
preserved when nothing else moved.
"""

import shutil
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from hornero.paths import contained_path

from hornero.sdd_toolkit.lock import (
    FileEntry,
    SddLock,
    load_lock,
    save_lock,
    sha256_file,
)
from hornero.sdd_toolkit.manifest import load_manifest, resolve_managed
from hornero.sdd_toolkit.upstream import fetch_upstream

Echo = Callable[[str], None]


def scaffold_dirs(repo_root: Path, dirs: list[str]) -> None:
    for rel in dirs:
        d = contained_path(repo_root, rel.rstrip("/"))
        d.mkdir(parents=True, exist_ok=True)
        (d / ".gitkeep").touch()


def install(
    repo_root: Path,
    source: str,
    ref: str,
    *,
    force: bool = False,
    synced_at: str = "",
    echo: Echo = print,
) -> int:
    checkout = fetch_upstream(source, ref, repo_root)
    if not checkout.refreshed:
        echo("warning: upstream unreachable — installing from a stale cache")
    manifest, from_fallback = load_manifest(checkout.root)
    if from_fallback:
        echo(
            "warning: upstream has no sdd-toolkit.manifest.json; "
            "using built-in fallback patterns"
        )

    entries: dict[str, FileEntry] = {}
    installed = adopted = kept = 0
    for rel in resolve_managed(checkout.root, manifest):
        src = contained_path(checkout.root, rel)
        dest = contained_path(repo_root, rel)
        upstream_hash = sha256_file(src)
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            installed_hash = upstream_hash
            installed += 1
        else:
            current_hash = sha256_file(dest)
            if current_hash == upstream_hash:
                installed_hash = upstream_hash
                adopted += 1
            elif force:
                shutil.copy2(src, dest)
                installed_hash = upstream_hash
                installed += 1
            else:  # adopt as modified — never clobber silently
                installed_hash = current_hash
                kept += 1
        entries[rel] = FileEntry(
            upstream_hash=upstream_hash, installed_hash=installed_hash
        )

    scaffold_dirs(repo_root, manifest.scaffold)

    from hornero.instructions import inject  # SPEC-003 §8, idempotent

    for name in inject(repo_root):
        echo(f"instruction section written: {name}")

    old = load_lock(repo_root)
    new = SddLock(
        upstream=source,
        upstream_ref=ref,
        toolkit_version=manifest.version,
        upstream_commit=checkout.commit,
        synced_at=synced_at,
        files={
            path: replace(
                entry,
                policy=old.files[path].policy
                if old and path in old.files
                else entry.policy,
            )
            for path, entry in entries.items()
        },
    )
    # Idempotency: identical except timestamp => keep the old lock verbatim.
    if old is not None and replace(new, synced_at=old.synced_at) == old:
        echo(
            f"toolkit {manifest.version}: up to date "
            f"({adopted + kept + installed} file(s) verified)"
        )
        return 0
    save_lock(repo_root, new)
    echo(
        f"toolkit {manifest.version}: {installed} installed, {adopted} adopted, "
        f"{kept} kept as locally modified, {len(manifest.scaffold)} dir(s) scaffolded"
    )
    return 0

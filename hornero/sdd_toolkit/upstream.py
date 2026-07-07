"""Upstream access (SPEC-002 §7 mechanics).

Two source shapes, one contract:

- a **local directory** (fixture upstreams, workspace-adjacent checkouts) —
  used in place; its HEAD sha recorded when it is a git repo;
- a **git URL** — shallow blobless clone into
  ``.hornero/cache/sdd-upstream/`` (gitignored), refreshed on each
  status/sync; a network failure with a warm cache degrades to the cache
  with ``refreshed=False`` (the caller warns about staleness) instead of
  failing the command.
"""

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

CACHE_SUBDIR = Path(".hornero") / "cache" / "sdd-upstream"


class UpstreamError(RuntimeError):
    pass


@dataclass(frozen=True)
class Checkout:
    root: Path
    commit: str | None
    refreshed: bool  # False => served from a stale cache (offline)


def _git(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    )


def _head(path: Path) -> str | None:
    try:
        return _git(["rev-parse", "HEAD"], cwd=path).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def fetch_upstream(source: str, ref: str, repo_root: Path) -> Checkout:
    src = Path(source)
    if src.is_dir():
        return Checkout(root=src.resolve(), commit=_head(src), refreshed=True)

    cache = repo_root / CACHE_SUBDIR
    if cache.is_dir() and (cache / ".git").exists():
        try:
            _git(["fetch", "--depth", "1", "origin", ref], cwd=cache)
            _git(["checkout", "-q", "--detach", "FETCH_HEAD"], cwd=cache)
            return Checkout(cache, _head(cache), refreshed=True)
        except (OSError, subprocess.CalledProcessError):
            return Checkout(cache, _head(cache), refreshed=False)

    cache.parent.mkdir(parents=True, exist_ok=True)
    try:
        _git([
            "clone", "--filter=blob:none", "--depth", "1",
            "--branch", ref, source, str(cache),
        ])
    except (OSError, subprocess.CalledProcessError) as exc:
        shutil.rmtree(cache, ignore_errors=True)  # never leave a half clone
        detail = exc.stderr.strip() if hasattr(exc, "stderr") and exc.stderr else str(exc)
        raise UpstreamError(
            f"cannot reach upstream {source!r} and no cache exists: {detail}"
        ) from exc
    return Checkout(cache, _head(cache), refreshed=True)

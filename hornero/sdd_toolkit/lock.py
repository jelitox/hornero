"""Per-repo lockfile ``.hornero/sdd.lock`` (SPEC-002 §5).

The L leg of the three-way drift model: for every managed file it records
the upstream hash and the installed hash at last sync, plus a policy
(``sync`` | ``local`` | ``pinned``). The lockfile is COMMITTED — it is the
repo's sync identity, not operational state.
"""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from hornero.paths import PathViolation, validate_relative_path

LOCK_NAME = "sdd.lock"
POLICIES = ("sync", "local", "pinned")


@dataclass
class FileEntry:
    upstream_hash: str
    installed_hash: str
    policy: str = "sync"

    def __post_init__(self) -> None:
        if self.policy not in POLICIES:
            raise ValueError(f"illegal policy {self.policy!r}; one of {POLICIES}")


@dataclass
class SddLock:
    upstream: str
    upstream_ref: str
    toolkit_version: str
    upstream_commit: str | None
    synced_at: str
    files: dict[str, FileEntry] = field(default_factory=dict)


def lock_path(repo_root: Path) -> Path:
    return repo_root / ".hornero" / LOCK_NAME


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_lock(repo_root: Path) -> SddLock | None:
    path = lock_path(repo_root)
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    try:
        files = {
            validate_relative_path(str(p)): FileEntry(**entry)
            for p, entry in data.get("files", {}).items()
        }
    except PathViolation as exc:
        raise ValueError(f"{path}: unsafe managed path: {exc}") from exc
    return SddLock(
        upstream=data["upstream"],
        upstream_ref=data["upstream_ref"],
        toolkit_version=data["toolkit_version"],
        upstream_commit=data.get("upstream_commit"),
        synced_at=data["synced_at"],
        files=files,
    )


def save_lock(repo_root: Path, lock: SddLock) -> Path:
    path = lock_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(lock)
    data["files"] = {p: asdict(e) for p, e in sorted(lock.files.items())}
    path.write_text(
        json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def set_policy(lock: SddLock, file: str, policy: str) -> None:
    if file not in lock.files:
        raise ValueError(f"{file!r} is not a managed file in the lock")
    if policy not in POLICIES:
        raise ValueError(f"illegal policy {policy!r}; one of {POLICIES}")
    lock.files[file].policy = policy

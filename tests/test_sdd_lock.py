"""Lockfile round-trip, determinism, policy validation."""

import pytest

from hornero.sdd_toolkit.lock import (
    FileEntry,
    SddLock,
    load_lock,
    lock_path,
    save_lock,
    set_policy,
    sha256_file,
)


def _lock():
    return SddLock(
        upstream="https://example.invalid/toolkit.git",
        upstream_ref="main",
        toolkit_version="2026.07.0",
        upstream_commit="a" * 40,
        synced_at="2026-07-07T00:00:00Z",
        files={
            ".claude/commands/sdd-start.md": FileEntry("u1", "i1"),
            ".claude/rules/python-development.md": FileEntry("u2", "i2", "local"),
        },
    )


def test_roundtrip_and_deterministic_bytes(tmp_path):
    save_lock(tmp_path, _lock())
    first = lock_path(tmp_path).read_bytes()
    loaded = load_lock(tmp_path)
    assert loaded == _lock()
    save_lock(tmp_path, loaded)
    assert lock_path(tmp_path).read_bytes() == first


def test_missing_lock_returns_none(tmp_path):
    assert load_lock(tmp_path) is None


def test_policy_validation(tmp_path):
    lock = _lock()
    with pytest.raises(ValueError, match="illegal policy"):
        FileEntry("u", "i", "newest-wins")
    with pytest.raises(ValueError, match="not a managed file"):
        set_policy(lock, "nope.md", "local")
    with pytest.raises(ValueError, match="illegal policy"):
        set_policy(lock, ".claude/commands/sdd-start.md", "yolo")
    set_policy(lock, ".claude/commands/sdd-start.md", "pinned")
    assert lock.files[".claude/commands/sdd-start.md"].policy == "pinned"


def test_sha256_file(tmp_path):
    p = tmp_path / "x.md"
    p.write_text("hello")
    assert sha256_file(p) == (
        "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    )

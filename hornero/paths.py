"""Filesystem trust-boundary helpers shared by mutable surfaces."""

from pathlib import Path, PurePosixPath


class PathViolation(ValueError):
    """A user/upstream-controlled path escapes its allowed root."""


def validate_relative_path(value: str, *, allow_glob: bool = False) -> str:
    """Return a normalized POSIX relative path or raise ``PathViolation``.

    Backslashes are rejected instead of normalized so a lock/manifest has one
    portable identity on every platform. Existing symlink escapes are checked
    separately by :func:`contained_path`.
    """
    if not isinstance(value, str) or not value.strip():
        raise PathViolation("path must be a non-empty string")
    if "\\" in value:
        raise PathViolation(f"path must use POSIX separators: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or value.startswith("/"):
        raise PathViolation(f"absolute path is not allowed: {value!r}")
    if any(part in ("", ".", "..") for part in path.parts):
        raise PathViolation(f"path traversal is not allowed: {value!r}")
    if not allow_glob and any(char in value for char in "*?[]"):
        raise PathViolation(f"glob characters are not allowed here: {value!r}")
    return path.as_posix()


def contained_path(root: Path, value: str) -> Path:
    """Resolve ``value`` below ``root``, rejecting traversal and symlink escape."""
    rel = validate_relative_path(value)
    base = root.resolve()
    candidate = (base / rel).resolve(strict=False)
    if not candidate.is_relative_to(base):
        raise PathViolation(f"path escapes allowed root {base}: {value!r}")
    return candidate

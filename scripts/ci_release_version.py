#!/usr/bin/env python3
"""Assign an immutable PEP 440 post-release version for a CI build."""

from __future__ import annotations

import argparse
import re
import tomllib
from pathlib import Path

_BASE_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_VERSION_LINE = re.compile(r'(?m)^(version\s*=\s*")[^"]+(".*)$')


def ci_release_version(base: str, run_number: int, run_attempt: int) -> str:
    """Return a unique, increasing post-release for a GitHub workflow run."""
    if not _BASE_VERSION.fullmatch(base):
        raise ValueError(
            f"project version {base!r} must be a stable MAJOR.MINOR.PATCH value"
        )
    if run_number < 1:
        raise ValueError("run number must be positive")
    if not 1 <= run_attempt <= 999:
        raise ValueError("run attempt must be between 1 and 999")
    return f"{base}.post{run_number * 1000 + run_attempt}"


def rewrite_project_version(path: Path, version: str) -> None:
    """Replace the single project version declaration in pyproject.toml."""
    original = path.read_text(encoding="utf-8")
    project_start = original.find("[project]")
    if project_start < 0:
        raise ValueError(f"{path}: [project] table is missing")
    next_table = original.find("\n[", project_start + len("[project]"))
    project_end = len(original) if next_table < 0 else next_table
    project = original[project_start:project_end]
    updated, replacements = _VERSION_LINE.subn(
        rf"\g<1>{version}\g<2>", project, count=1
    )
    if replacements != 1:
        raise ValueError(f"{path}: [project].version declaration is missing")
    path.write_text(
        original[:project_start] + updated + original[project_end:],
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pyproject", type=Path, default=Path("pyproject.toml"))
    parser.add_argument("--run-number", type=int, required=True)
    parser.add_argument("--run-attempt", type=int, required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    with args.pyproject.open("rb") as handle:
        base = tomllib.load(handle)["project"]["version"]
    version = ci_release_version(base, args.run_number, args.run_attempt)
    if args.write:
        rewrite_project_version(args.pyproject, version)
    print(version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

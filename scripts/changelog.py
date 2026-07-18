#!/usr/bin/env python3
"""Validate changelog fragments and project release notes into PyPI metadata."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


CATEGORY_TITLES = {
    "added": "Added",
    "changed": "Changed",
    "deprecated": "Deprecated",
    "removed": "Removed",
    "fixed": "Fixed",
    "security": "Security",
    "dependencies": "Dependencies",
}
RELEASE_NOTES_START = "<!-- pypi-release-notes:start -->"
RELEASE_NOTES_END = "<!-- pypi-release-notes:end -->"
_FRAGMENT_NAME = re.compile(
    r"^(?P<identifier>[A-Za-z0-9][A-Za-z0-9_-]*)\."
    r"(?P<category>added|changed|deprecated|removed|fixed|security|dependencies)"
    r"\.md$"
)


@dataclass(frozen=True)
class Fragment:
    path: Path
    identifier: str
    category: str
    text: str


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ValueError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout.strip()


def _relative_to_root(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"{path} must be inside repository {root}") from exc


def parse_fragment(path: Path) -> Fragment:
    match = _FRAGMENT_NAME.fullmatch(path.name)
    if match is None:
        categories = ", ".join(CATEGORY_TITLES)
        raise ValueError(
            f"{path}: expected NAME.CATEGORY.md; CATEGORY must be one of {categories}"
        )
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"{path}: fragment must not be empty")
    if text.startswith("- "):
        text = text[2:].strip()
    if not text:
        raise ValueError(f"{path}: fragment must contain a change description")
    return Fragment(
        path=path,
        identifier=match.group("identifier"),
        category=match.group("category"),
        text=text,
    )


def load_fragments(directory: Path) -> list[Fragment]:
    if not directory.is_dir():
        raise ValueError(f"{directory}: changelog fragment directory is missing")
    fragments: list[Fragment] = []
    for path in sorted(directory.glob("*.md")):
        if path.name == "README.md":
            continue
        fragments.append(parse_fragment(path))
    return fragments


def _changed_fragment_paths(
    root: Path,
    directory: Path,
    before: str,
    after: str,
    *,
    merge_base: bool,
) -> list[Path]:
    relative_directory = _relative_to_root(directory, root)
    separator = "..." if merge_base else ".."
    output = _git(
        root,
        "diff",
        "--name-only",
        "--diff-filter=AM",
        f"{before}{separator}{after}",
        "--",
        relative_directory,
    )
    paths = [root / line for line in output.splitlines() if line]
    return [path for path in paths if path.name != "README.md"]


def render_fragments(fragments: list[Fragment]) -> str:
    sections: list[str] = []
    for category, title in CATEGORY_TITLES.items():
        entries = [fragment for fragment in fragments if fragment.category == category]
        if not entries:
            continue
        lines = [f"### {title}", ""]
        for fragment in entries:
            continuation = fragment.text.replace("\n", "\n  ")
            lines.append(f"- {continuation}")
        sections.append("\n".join(lines))
    return "\n\n".join(sections)


def _resolve_commit(root: Path, revision: str) -> str:
    return _git(root, "rev-parse", "--verify", f"{revision}^{{commit}}")


def _resolve_before(root: Path, before: str, after_sha: str) -> str:
    if before and set(before) != {"0"}:
        try:
            return _resolve_commit(root, before)
        except ValueError:
            pass
    return _resolve_commit(root, f"{after_sha}^")


def _commit_subjects(root: Path, before_sha: str, after_sha: str) -> list[str]:
    output = _git(
        root,
        "log",
        "--reverse",
        "--format=%s",
        "--no-merges",
        f"{before_sha}..{after_sha}",
    )
    subjects = [line.strip() for line in output.splitlines() if line.strip()]
    if subjects:
        return subjects
    fallback = _git(
        root,
        "log",
        "--reverse",
        "--format=%s",
        f"{before_sha}..{after_sha}",
    )
    return [line.strip() for line in fallback.splitlines() if line.strip()]


def prepare_pypi_readme(
    root: Path,
    directory: Path,
    readme: Path,
    version: str,
    before: str,
    after: str,
    repository_url: str,
) -> str:
    after_sha = _resolve_commit(root, after)
    before_sha = _resolve_before(root, before, after_sha)
    changed_paths = _changed_fragment_paths(
        root,
        directory,
        before_sha,
        after_sha,
        merge_base=False,
    )
    fragments = [parse_fragment(path) for path in changed_paths]
    rendered = render_fragments(fragments)
    if not rendered:
        subjects = _commit_subjects(root, before_sha, after_sha)
        if not subjects:
            subjects = ["Rebuilt the current master revision."]
        rendered = "### Changed\n\n" + "\n".join(
            f"- {subject}" for subject in subjects
        )

    repository_url = repository_url.rstrip("/")
    links = (
        f"[Full changelog]({repository_url}/blob/{after_sha}/CHANGELOG.md) · "
        f"[Compare changes]({repository_url}/compare/{before_sha}...{after_sha})"
    )
    release_notes = (
        f"{RELEASE_NOTES_START}\n"
        f"## What's new in {version}\n\n"
        f"{rendered}\n\n"
        f"{links}\n"
        f"{RELEASE_NOTES_END}"
    )

    original = readme.read_text(encoding="utf-8")
    pattern = re.compile(
        re.escape(RELEASE_NOTES_START)
        + r".*?"
        + re.escape(RELEASE_NOTES_END),
        re.DOTALL,
    )
    updated, replacements = pattern.subn(release_notes, original, count=1)
    if replacements != 1:
        raise ValueError(
            f"{readme}: expected exactly one PyPI release-notes marker block"
        )
    return updated


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--directory", type=Path, default=Path(".changes"))
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate")
    validate.add_argument("--base-ref")
    validate.add_argument("--head-ref", default="HEAD")
    validate.add_argument("--require-new", action="store_true")

    commands.add_parser("preview")

    prepare = commands.add_parser("prepare-pypi")
    prepare.add_argument("--version", required=True)
    prepare.add_argument("--before", default="")
    prepare.add_argument("--after", default="HEAD")
    prepare.add_argument("--repository-url", required=True)
    prepare.add_argument("--readme", type=Path, default=Path("README.md"))
    prepare.add_argument("--write", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    root = args.root.resolve()
    directory = args.directory
    if not directory.is_absolute():
        directory = root / directory

    try:
        fragments = load_fragments(directory)
        if args.command == "validate":
            if args.require_new:
                if not args.base_ref:
                    raise ValueError("--require-new also requires --base-ref")
                changed = _changed_fragment_paths(
                    root,
                    directory,
                    args.base_ref,
                    args.head_ref,
                    merge_base=True,
                )
                if not changed:
                    raise ValueError(
                        "this change requires a new .changes/NAME.CATEGORY.md fragment"
                    )
                for path in changed:
                    parse_fragment(path)
            print(f"Validated {len(fragments)} changelog fragment(s).")
            return 0

        if args.command == "preview":
            print(render_fragments(fragments) or "No unreleased changelog fragments.")
            return 0

        readme = args.readme
        if not readme.is_absolute():
            readme = root / readme
        updated = prepare_pypi_readme(
            root=root,
            directory=directory,
            readme=readme,
            version=args.version,
            before=args.before,
            after=args.after,
            repository_url=args.repository_url,
        )
        if args.write:
            readme.write_text(updated, encoding="utf-8")
        else:
            print(updated)
        return 0
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"changelog: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

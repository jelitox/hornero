"""Spec lifecycle: frontmatter contract + state machine + corpus (SPEC-001 §5).

Spec files under ``sdd/specs/`` ARE the tracker. This module owns the
YAML-frontmatter parse/serialize round-trip (byte-identical for unmodified
docs, so transitions produce minimal reviewable diffs), the legal status
transitions, and monotonic id allocation (§4).
"""

import re
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path

import yaml


class Status(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    BUILDING = "building"
    REVIEW = "review"
    DONE = "done"
    REJECTED = "rejected"
    NEEDS_HUMAN = "needs_human"
    OBSOLETE = "obsolete"


# The §5 diagram. `obsolete` is reachable from every state except the other
# terminals — an approved OBSOLETE delta can invalidate even a `done` spec
# (a built product can still be invalidated by a new signal).
TRANSITIONS: dict[Status, set[Status]] = {
    Status.PROPOSED: {Status.APPROVED, Status.REJECTED, Status.OBSOLETE},
    Status.APPROVED: {Status.BUILDING, Status.OBSOLETE},
    Status.BUILDING: {Status.REVIEW, Status.NEEDS_HUMAN, Status.OBSOLETE},
    Status.REVIEW: {Status.DONE, Status.OBSOLETE},
    Status.NEEDS_HUMAN: {Status.APPROVED, Status.OBSOLETE},
    Status.DONE: {Status.OBSOLETE},
    Status.REJECTED: set(),
    Status.OBSOLETE: set(),
}

_FENCE = "---\n"
_STATUS_LINE = re.compile(r"^(status:[ \t]*)([^\s#]+)(.*)$", re.MULTILINE)
_SPEC_ID = re.compile(r"^SPEC-(\d+)$")


class IllegalTransition(Exception):
    """Raised when a status change is not an edge of the §5 diagram."""


class SpecParseError(ValueError):
    """Raised when a spec file violates the frontmatter contract."""


@dataclass(frozen=True)
class SpecDoc:
    """One parsed spec file. ``raw_frontmatter`` preserves the original
    frontmatter text (extra keys, comments, ordering) so writing an
    unmodified doc is byte-identical."""

    path: Path
    spec_id: str
    title: str
    status: Status
    kind: str
    created: str
    sources: list[str]
    supersedes: list[str]
    acceptance_criteria: list[str]
    body: str
    raw_frontmatter: str


def parse_spec(path: Path) -> SpecDoc:
    text = path.read_text(encoding="utf-8")
    if not text.startswith(_FENCE):
        raise SpecParseError(f"{path}: missing frontmatter opening fence")
    end = text.find(f"\n{_FENCE}", len(_FENCE) - 1)
    if end < 0:
        raise SpecParseError(f"{path}: missing frontmatter closing fence")
    raw_fm = text[len(_FENCE) : end + 1]
    body = text[end + 1 + len(_FENCE) :]

    meta = yaml.safe_load(raw_fm)
    if not isinstance(meta, dict):
        raise SpecParseError(f"{path}: frontmatter is not a mapping")

    def _req(key: str) -> str:
        if key not in meta or meta[key] in (None, ""):
            raise SpecParseError(f"{path}: frontmatter missing required key '{key}'")
        return str(meta[key])

    raw_status = _req("status")
    try:
        status = Status(raw_status)
    except ValueError as exc:  # fail-closed: never coerce unknown states
        raise SpecParseError(f"{path}: unknown status '{raw_status}'") from exc

    def _lst(key: str) -> list[str]:
        val = meta.get(key) or []
        if not isinstance(val, list):
            raise SpecParseError(f"{path}: frontmatter '{key}' must be a list")
        return [str(v) for v in val]

    return SpecDoc(
        path=path,
        spec_id=_req("spec"),
        title=_req("title"),
        status=status,
        kind=str(meta.get("kind", "")),
        created=str(meta.get("created", "")),
        sources=_lst("sources"),
        supersedes=_lst("supersedes"),
        acceptance_criteria=_lst("acceptance_criteria"),
        body=body,
        raw_frontmatter=raw_fm,
    )


def write_spec(doc: SpecDoc) -> None:
    doc.path.write_text(
        f"{_FENCE}{doc.raw_frontmatter}{_FENCE}{doc.body}", encoding="utf-8"
    )


def transition(doc: SpecDoc, new_status: Status | str) -> SpecDoc:
    """Return a copy of ``doc`` moved to ``new_status``, rewriting only the
    ``status:`` line of the frontmatter. Raises :class:`IllegalTransition`
    for non-edges; does not write to disk."""
    target = Status(new_status)
    if target not in TRANSITIONS[doc.status]:
        raise IllegalTransition(
            f"{doc.spec_id}: {doc.status.value} -> {target.value} is not a legal edge"
        )
    new_fm, n = _STATUS_LINE.subn(rf"\g<1>{target.value}\g<3>", doc.raw_frontmatter, count=1)
    if n != 1:
        raise SpecParseError(f"{doc.spec_id}: no status line found in frontmatter")
    return replace(doc, status=target, raw_frontmatter=new_fm)


class SpecCorpus:
    """All ``SPEC-*.md`` files under a specs directory."""

    def __init__(self, specs_dir: Path) -> None:
        self.specs_dir = specs_dir
        self.docs: list[SpecDoc] = []
        if specs_dir.is_dir():
            # OQ8: both naming conventions load — this repo's SPEC-NNN-<slug>.md
            # and ai-parrot-style <slug>.spec.md.
            paths = {p for p in specs_dir.glob("SPEC-*.md")}
            paths |= {p for p in specs_dir.glob("*.spec.md")}
            for p in sorted(paths):
                self.docs.append(parse_spec(p))
        self.by_id: dict[str, SpecDoc] = {d.spec_id: d for d in self.docs}

    def next_spec_id(self) -> str:
        """Monotonic per repo (§4): max existing number + 1."""
        highest = 0
        for doc in self.docs:
            m = _SPEC_ID.match(doc.spec_id)
            if m:
                highest = max(highest, int(m.group(1)))
        return f"SPEC-{highest + 1:03d}"

    def counts_by_status(self) -> dict[Status, int]:
        counts = {s: 0 for s in Status}
        for doc in self.docs:
            counts[doc.status] += 1
        return counts

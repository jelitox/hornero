"""Apply step: approved deltas mutate the repo (SPEC-001 §9 step 5).

The ONLY writer of ``product/specs/`` in the reconcile pipeline, and it
re-checks the approval guard itself (defense in depth over the HITL gate):
anything not APPROVED/EDITED contributes zero filesystem writes. Unified
diffs apply with exact context or fail that delta cleanly — never fuzzy,
never partial.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

from hornero.lifecycle import SpecCorpus, SpecParseError, parse_spec
from hornero.models import DeltaKind, RequirementDelta
from hornero.ports import SignalSource, TrackerPort
from hornero.reconciler.hitl import Decision, ReviewedDelta

_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_ADR_ID = re.compile(r"ADR-(\d+)")
_SPEC_LINE = re.compile(r"^spec:[ \t]*\S+", re.MULTILINE)
_STATUS_LINE = re.compile(r"^status:[ \t]*\S+", re.MULTILINE)
_SOURCES_LINE = re.compile(r"^sources:[ \t]*.*$", re.MULTILINE)


class PatchError(Exception):
    """Unified diff did not apply with exact context."""


@dataclass
class ApplyReport:
    created: list[str] = field(default_factory=list)
    patched: list[str] = field(default_factory=list)
    obsoleted: list[str] = field(default_factory=list)
    proposals: list[str] = field(default_factory=list)  # SPEC-002 §2
    adrs: list[str] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)
    acked_signals: list[str] = field(default_factory=list)


def apply_unified_diff(original: str, diff: str) -> str:
    """Exact-context unified diff application. Context or deletion lines that
    do not match the original raise :class:`PatchError`; nothing is returned
    partially applied."""
    old = original.splitlines()
    out: list[str] = []
    cursor = 0  # index into old
    lines = [ln for ln in diff.splitlines() if not ln.startswith(("---", "+++"))]
    i = 0
    saw_hunk = False
    while i < len(lines):
        m = _HUNK.match(lines[i])
        if not m:
            i += 1
            continue
        saw_hunk = True
        start = int(m.group(1)) - 1  # 0-based position in old
        if start < cursor:
            raise PatchError(f"overlapping hunks at line {start + 1}")
        out.extend(old[cursor:start])
        cursor = start
        i += 1
        while i < len(lines) and not _HUNK.match(lines[i]):
            ln = lines[i]
            if ln.startswith("+"):
                out.append(ln[1:])
            elif ln.startswith(("-", " ")) or ln == "":
                expected = ln[1:] if ln else ""
                if cursor >= len(old) or old[cursor] != expected:
                    got = old[cursor] if cursor < len(old) else "<EOF>"
                    raise PatchError(
                        f"context mismatch at line {cursor + 1}: "
                        f"expected {expected!r}, found {got!r}"
                    )
                if not ln.startswith("-"):
                    out.append(old[cursor])
                cursor += 1
            elif ln.startswith("\\"):  # "\ No newline at end of file"
                pass
            else:
                raise PatchError(f"malformed diff line: {ln!r}")
            i += 1
    if not saw_hunk:
        raise PatchError("no hunks found in patch")
    out.extend(old[cursor:])
    text = "\n".join(out)
    if original.endswith("\n"):
        text += "\n"
    return text


def _slug(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:40] or "untitled"


def _signal_ids(delta: RequirementDelta) -> list[str]:
    seen: list[str] = []
    for ev in delta.evidence:
        if ev.signal_id not in seen:
            seen.append(ev.signal_id)
    return seen


def _prepare_new_spec_text(patch: str, spec_id: str, sources: list[str]) -> str:
    text = patch if patch.endswith("\n") else patch + "\n"
    text, n = _SPEC_LINE.subn(f"spec: {spec_id}", text, count=1)
    if n != 1:
        raise SpecParseError("proposed_patch has no 'spec:' frontmatter line")
    text = _STATUS_LINE.sub("status: proposed", text, count=1)
    src = f"sources: [{', '.join(sources)}]"
    text, n = _SOURCES_LINE.subn(src, text, count=1)
    if n != 1:  # insert right after the spec line
        text = re.sub(
            r"(^spec:[^\n]*\n)", rf"\g<1>{src}\n", text, count=1, flags=re.MULTILINE
        )
    return text


def _merge_sources(path: Path, new_ids: list[str]) -> None:
    doc = parse_spec(path)
    merged = list(dict.fromkeys([*doc.sources, *new_ids]))
    src = f"sources: [{', '.join(merged)}]"
    text = path.read_text(encoding="utf-8")
    text, n = _SOURCES_LINE.subn(src, text, count=1)
    if n != 1:
        text = re.sub(
            r"(^spec:[^\n]*\n)", rf"\g<1>{src}\n", text, count=1, flags=re.MULTILINE
        )
    path.write_text(text, encoding="utf-8")


def _adr_mentions(decisions_dir: Path, spec_id: str) -> bool:
    if not decisions_dir.is_dir():
        return False
    return any(
        spec_id in p.read_text(encoding="utf-8", errors="replace")
        for p in sorted(decisions_dir.glob("ADR-*.md"))
    )


def _next_adr_id(decisions_dir: Path) -> str:
    highest = 0
    if decisions_dir.is_dir():
        for p in decisions_dir.glob("ADR-*.md"):
            m = _ADR_ID.search(p.name)
            if m:
                highest = max(highest, int(m.group(1)))
    return f"ADR-{highest + 1:03d}"


def _write_adr(
    decisions_dir: Path, delta: RequirementDelta, spec_id: str, today: str
) -> str:
    adr_id = _next_adr_id(decisions_dir)
    decisions_dir.mkdir(parents=True, exist_ok=True)
    evidence = "\n".join(
        f"- {ev.signal_id} @ {ev.locator}: {ev.excerpt!r}" for ev in delta.evidence
    )
    (decisions_dir / f"{adr_id}-{_slug(delta.title)}.md").write_text(
        f"# {adr_id} — {delta.title}\n\n"
        f"- Date: {today}\n"
        f"- Reverses/updates a prior decision about: {spec_id}\n"
        f"- Caused by delta: {delta.delta_id} ({delta.kind.value})\n\n"
        f"## Summary\n\n{delta.summary}\n\n"
        f"## Evidence\n\n{evidence}\n",
        encoding="utf-8",
    )
    return adr_id


def _write_proposal(
    proposals_dir: Path,
    templates_dir: Path,
    delta: RequirementDelta,
    today: str,
) -> str:
    """SPEC-002 §2: a NEW delta whose patch is not a valid spec becomes a
    brainstorm proposal in ``sdd/proposals/`` instead of an error."""
    proposals_dir.mkdir(parents=True, exist_ok=True)
    name = f"{_slug(delta.title)}.brainstorm.md"
    evidence = "\n".join(
        f"- {ev.signal_id} @ {ev.locator}: {ev.excerpt!r}" for ev in delta.evidence
    )
    template = templates_dir / "brainstorm.md"
    header = (
        template.read_text(encoding="utf-8").strip() + "\n\n---\n\n"
        if template.is_file()
        else ""
    )
    (proposals_dir / name).write_text(
        f"{header}# Brainstorm: {delta.title}\n\n"
        f"- Date: {today}\n- Origin delta: {delta.delta_id} "
        f"(confidence {delta.confidence:.2f})\n\n"
        f"## Summary\n\n{delta.summary}\n\n"
        f"## Evidence\n\n{evidence}\n\n"
        f"## Raw proposal\n\n{delta.proposed_patch}\n",
        encoding="utf-8",
    )
    return name


def apply_deltas(
    reviewed: list[ReviewedDelta],
    corpus: SpecCorpus,
    tracker: TrackerPort,
    source: SignalSource,
    *,
    decisions_dir: Path,
    proposals_dir: Path,
    templates_dir: Path,
    today: str,
) -> ApplyReport:
    report = ApplyReport()
    created_ids: list[str] = []
    failed_delta_ids: set[str] = set()

    def _next_spec_id() -> str:
        highest = 0
        for sid in [*corpus.by_id, *created_ids]:
            m = re.match(r"^SPEC-(\d+)$", sid)
            if m:
                highest = max(highest, int(m.group(1)))
        return f"SPEC-{highest + 1:03d}"

    for item in reviewed:
        delta, decision = item.delta, item.result.decision
        if decision not in (Decision.APPROVED, Decision.EDITED):
            continue  # guard: zero writes for anything not human-approved
        patch = (
            item.result.patch
            if decision is Decision.EDITED and item.result.patch is not None
            else delta.proposed_patch
        )
        try:
            if delta.kind is DeltaKind.NEW:
                # §2 routing: a patch carrying valid spec frontmatter becomes
                # a spec; anything else becomes a brainstorm proposal.
                try:
                    spec_id = _next_spec_id()
                    text = _prepare_new_spec_text(patch, spec_id, _signal_ids(delta))
                except SpecParseError:
                    report.proposals.append(
                        _write_proposal(proposals_dir, templates_dir, delta, today)
                    )
                    continue
                path = corpus.specs_dir / f"{spec_id}-{_slug(delta.title)}.md"
                path.write_text(text, encoding="utf-8")
                try:
                    parse_spec(path)  # must be a valid spec or nothing lands
                except SpecParseError:
                    path.unlink()
                    report.proposals.append(
                        _write_proposal(proposals_dir, templates_dir, delta, today)
                    )
                    continue
                created_ids.append(spec_id)
                tracker.transition(spec_id, "approved")
                tracker.comment(
                    spec_id,
                    f"created from {delta.delta_id} "
                    f"(evidence: {', '.join(_signal_ids(delta))}); approved via HITL.",
                )
                report.created.append(spec_id)

            elif delta.kind is DeltaKind.CHANGED:
                for ref in delta.affected_specs:
                    doc = corpus.by_id.get(ref)
                    if doc is None:
                        raise KeyError(f"affected spec {ref} not found")
                    original = doc.path.read_text(encoding="utf-8")
                    patched = apply_unified_diff(original, patch)
                    doc.path.write_text(patched, encoding="utf-8")
                    parse_spec(doc.path)  # patched file must still be valid
                    _merge_sources(doc.path, _signal_ids(delta))
                    tracker.comment(
                        ref,
                        f"changed by {delta.delta_id} "
                        f"(evidence: {', '.join(_signal_ids(delta))}).",
                    )
                    if _adr_mentions(decisions_dir, ref):
                        report.adrs.append(_write_adr(decisions_dir, delta, ref, today))
                    report.patched.append(ref)

            elif delta.kind is DeltaKind.OBSOLETE:
                for ref in delta.affected_specs:
                    tracker.transition(ref, "obsolete")
                    tracker.comment(
                        ref,
                        f"obsoleted by {delta.delta_id} "
                        f"(evidence: {', '.join(_signal_ids(delta))}).",
                    )
                    if _adr_mentions(decisions_dir, ref):
                        report.adrs.append(_write_adr(decisions_dir, delta, ref, today))
                    report.obsoleted.append(ref)
            # DUPLICATE never reaches here: gate() always marks it SKIPPED.
        except Exception as exc:  # per-delta isolation: one failure never
            failed_delta_ids.add(delta.delta_id)  # aborts the whole batch
            report.errors.append((delta.delta_id, str(exc)))

    # Ack a signal only when it got at least one human decision and none of
    # its approved deltas failed to apply. Pure-SKIPPED signals stay in the
    # inbox (fail-closed: no human, no effect).
    by_signal: dict[str, list[ReviewedDelta]] = {}
    for item in reviewed:
        for sid in _signal_ids(item.delta):
            by_signal.setdefault(sid, []).append(item)
    for sid, items in sorted(by_signal.items()):
        decided = [i for i in items if i.result.decision is not Decision.SKIPPED]
        if not decided:
            continue
        if any(i.delta.delta_id in failed_delta_ids for i in decided):
            continue
        source.ack(sid)
        report.acked_signals.append(sid)
    return report

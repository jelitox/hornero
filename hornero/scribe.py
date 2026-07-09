"""The scribe (SPEC-004 §4): trace -> Decision Record.

Epistemological ground rule: the DR is an INDEX over the action stream,
never evidence on its own. Hence S1-S4:

- S1: every claim carries an event-range citation resolving to real events;
  a claim the scribe cannot anchor is DROPPED and ledger-logged, never kept.
- S2: the scribe reads the trace, not the builder's memory — its only
  inputs are the trace file and the spec.
- S3: ``thinking_summary`` events may inform tone but never suffice — at
  least one action event (tool_use/tool_result/error) anchors every claim.
- S4: a trivial run (no action events) yields NO DR; "no decision content"
  goes to the run log instead of a fabricated narrative.
"""

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from hornero import flight, layout
from hornero.memory.ledger import Ledger
from hornero.reconciler.draft import LLMPort
from hornero.redact import redact

Echo = Callable[[str], None]

ACTION_KINDS = {"tool_use", "tool_result", "error"}

SECTIONS = (
    ("approach", "Approach taken"),
    ("alternatives", "Alternatives considered and rejected"),
    ("deviations", "Deviations from plan / spec"),
    ("failures", "Failures and retries"),
    ("learnings", "Learnings for future runs"),
)

SCRIBE_SYSTEM = """\
You are hornero's scribe. Distill ONE run's trace into a decision record as
STRICT JSON:

{"title": "...", "sections": {
  "approach": [{"text": "...", "cite": "e#12-e#40"}],
  "alternatives": [{"text": "...", "cite": "e#55-e#61"}],
  "deviations": [{"text": "...", "cite": "e#88"}],
  "failures": [{"text": "...", "cite": "e#70-e#79"}],
  "learnings": [{"text": "...", "cite": "e#95"}]}}

Rules: summarize what HAPPENED per the events, not what anyone felt
happened. Every claim MUST cite the event range that evidences it; ranges
must contain at least one action event (tool_use/tool_result/error) —
thinking summaries alone never anchor a claim. Unsupported claims are
mechanically dropped. Empty lists are legitimate. Output JSON only.
"""

_CITE = re.compile(r"^e#(\d+)(?:\s*[-:]\s*e#(\d+))?$")


class ScribeError(RuntimeError):
    pass


def _parse_cite(cite: str) -> tuple[int, int] | None:
    m = _CITE.match(cite.strip())
    if not m:
        return None
    lo = int(m.group(1))
    hi = int(m.group(2)) if m.group(2) else lo
    return (lo, hi) if lo <= hi else None


def _render_events(events: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"e#{e['seq']} [{e['kind']}] {e['summary']}" for e in events
    )


def _next_dr_id(decisions_dir: Path) -> str:
    highest = 0
    for p in decisions_dir.glob("DR-*.md"):
        m = re.match(r"DR-(\d+)", p.name)
        if m:
            highest = max(highest, int(m.group(1)))
    return f"DR-{highest + 1:03d}"


def _existing_dr(decisions_dir: Path, run_ref: str) -> Path | None:
    for p in sorted(decisions_dir.glob("DR-*.md")):
        if f"run_id: {run_ref}" in p.read_text(encoding="utf-8"):
            return p
    return None


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:48] or "run"


def scribe_run(
    root: Path,
    run_ref: str,
    llm: LLMPort,
    *,
    today: str,
    force: bool = False,
    echo: Echo = print,
) -> int:
    events = flight.read_trace(root, run_ref)
    seqs = {int(e["seq"]) for e in events}
    action_seqs = {int(e["seq"]) for e in events if e["kind"] in ACTION_KINDS}

    if not action_seqs:  # S4: no actions => no decision content, no DR
        echo(f"{run_ref}: no decision content (no action events) — no DR")
        return 0

    decisions_dir = layout.decisions_dir(root)
    decisions_dir.mkdir(parents=True, exist_ok=True)
    existing = _existing_dr(decisions_dir, run_ref)
    if existing is not None and not force:
        echo(f"{run_ref}: already scribed as {existing.name} (use --force)")
        return 0

    with Ledger(root / ".hornero" / "ledger.db") as ledger:
        runs = [r for r in ledger.agent_runs() if r["run_ref"] == run_ref]
        meta = runs[0] if runs else {}

        spec_block = "(no spec linked)"
        spec_id = meta.get("spec_id")
        if spec_id:
            for p in layout.specs_dir(root).glob(f"{spec_id}-*.md"):
                spec_block = p.read_text(encoding="utf-8")[:4000]
                break

        # S2: trace + spec are the ONLY inputs.
        user = (
            f"## Trace of {run_ref}\n\n{_render_events(events)}\n\n"
            f"## Spec context\n\n{spec_block}"
        )
        try:
            data = json.loads(llm.complete(SCRIBE_SYSTEM, user))
        except json.JSONDecodeError as exc:
            raise ScribeError(f"scribe model returned invalid JSON: {exc}") from exc

        verified: dict[str, list[tuple[str, str]]] = {}
        for key, _heading in SECTIONS:
            for claim in (data.get("sections") or {}).get(key, []):
                text = str(claim.get("text", "")).strip()
                cite = str(claim.get("cite", "")).strip()
                span = _parse_cite(cite)
                # S1: every cited seq must be a real event; S3: the range
                # must contain at least one ACTION event.
                valid = (
                    bool(text)
                    and span is not None
                    and all(s in seqs for s in range(span[0], span[1] + 1))
                    and any(s in action_seqs for s in range(span[0], span[1] + 1))
                )
                if not valid:
                    ledger.record_dropped_draft(
                        run_ref, "unanchored_claim",
                        {"section": key, "text": text[:200], "cite": cite},
                        0.0,
                    )
                    echo(f"dropped unanchored claim ({key}): {text[:60]!r}")
                    continue
                verified.setdefault(key, []).append((text, cite))

        if not any(verified.values()):
            echo(f"{run_ref}: no verifiable decision content — no DR")
            return 0

        if existing is not None:
            match = re.match(r"(DR-\d+)", existing.name)
            assert match is not None
            dr_id = match.group(1)
        else:
            dr_id = _next_dr_id(decisions_dir)
        title = str(data.get("title") or f"run {run_ref}").strip()

        lines = [
            "---",
            f"dr: {dr_id}",
            f"run_id: {run_ref}",
            f"spec: {spec_id or '(none)'}",
            f"date: {today}",
            f"actor: {meta.get('actor', '(unknown)')}",
            f"outcome: {meta.get('status', '(unknown)')}",
            "---",
            "",
            f"# {dr_id} — {title}",
        ]
        for key, heading in SECTIONS:
            claims = verified.get(key, [])
            if not claims:
                continue
            lines += ["", f"## {heading}", ""]
            lines += [f"- {text} [{cite}]" for text, cite in claims]
        path = existing or decisions_dir / f"{dr_id}-{_slug(title)}.md"
        path.write_text(redact("\n".join(lines) + "\n"), encoding="utf-8")
        echo(f"wrote {path}")
    return 0

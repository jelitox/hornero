"""Lossless trace offload: evidence refs -> step summaries -> Mermaid canvas."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from hornero import flight
from hornero.redact import redact

ACTION_KINDS = {"tool_use", "tool_result", "error", "retry", "hitl.request", "hitl.decision"}


def _safe(value: str, limit: int = 160) -> str:
    compact = " ".join(redact(value).split())[:limit]
    return compact.replace("\\", "\\\\").replace('"', "'").replace("[", "(").replace("]", ")")


def _ref_name(seq: int) -> str:
    return f"e{seq:06d}.md"


def build(root: Path, run_ref: str) -> dict[str, Any]:
    """Rebuild the compact projection from the authoritative trace."""
    events = flight.read_trace(root, run_ref)
    run_dir = flight.runs_dir(root) / run_ref
    refs = run_dir / "refs"
    refs.mkdir(parents=True, exist_ok=True)
    steps: list[dict[str, Any]] = []
    action_nodes: list[dict[str, Any]] = []
    for event in events:
        seq = int(event["seq"])
        ref = refs / _ref_name(seq)
        ref.write_text(
            f"# Event e#{seq}\n\n"
            f"- Kind: `{event['kind']}`\n- Actor: `{event['actor']}`\n"
            f"- Summary: {redact(str(event['summary']))}\n\n"
            "```json\n"
            + json.dumps(event, indent=2, sort_keys=True, ensure_ascii=False)
            + "\n```\n",
            encoding="utf-8",
        )
        step = {
            "node_id": f"e{seq}", "seq": seq, "kind": str(event["kind"]),
            "summary": redact(str(event["summary"]))[:320],
            "ref": f"refs/{ref.name}",
        }
        steps.append(step)
        if event["kind"] in ACTION_KINDS or event["kind"] in {"run.started", "run.finished"}:
            action_nodes.append(step)
    steps_path = run_dir / "steps.jsonl"
    steps_path.write_text(
        "".join(json.dumps(step, sort_keys=True, ensure_ascii=False) + "\n" for step in steps),
        encoding="utf-8",
    )
    lines = ["flowchart TD"]
    for step in action_nodes:
        lines.append(
            f"  {step['node_id']}[\"e#{step['seq']} {step['kind']}: "
            f"{_safe(str(step['summary']))}\"]"
        )
    for left, right in zip(action_nodes, action_nodes[1:]):
        lines.append(f"  {left['node_id']} --> {right['node_id']}")
    errors = [step for step in action_nodes if step["kind"] in {"error", "retry"}]
    if errors:
        lines.append("  classDef failure fill:#fee2e2,stroke:#dc2626")
        lines.append("  class " + ",".join(step["node_id"] for step in errors) + " failure")
    canvas_path = run_dir / "canvas.md"
    canvas_path.write_text(
        f"# Symbolic canvas — {run_ref}\n\n```mermaid\n"
        + "\n".join(lines) + "\n```\n\n"
        "Drill down with `hornero runs drilldown " + run_ref + " eN`.\n",
        encoding="utf-8",
    )
    return {
        "run_ref": run_ref, "events": len(events), "action_nodes": len(action_nodes),
        "refs": str(refs), "steps": str(steps_path), "canvas": str(canvas_path),
    }


def drilldown(root: Path, run_ref: str, node_id: str) -> dict[str, Any]:
    match = re.fullmatch(r"e#?(\d+)", node_id.strip())
    if not match:
        raise ValueError("node id must be eN or e#N")
    seq = int(match.group(1))
    events = flight.read_trace(root, run_ref)
    event = next((item for item in events if int(item["seq"]) == seq), None)
    if event is None:
        raise KeyError(node_id)
    return event

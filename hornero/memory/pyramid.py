"""Layered project memory, bounded recall, persona and skill proposals."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from hornero import flight, layout
from hornero.memory import codegraph
from hornero.redact import redact

PYRAMID_PATH = Path(".hornero") / "knowledge" / "pyramid.json"
_SPEC = re.compile(r"\bSPEC-\d+\b")
_TOKEN = re.compile(r"[a-z0-9_]+")
_LEARNING = re.compile(r"^-\s+(.+?)\s+\[(e#\d+(?:[-:]e#\d+)?)\]\s*$")


def pyramid_path(root: Path) -> Path:
    return root / PYRAMID_PATH


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end < 0:
        return {}, text
    try:
        data = yaml.safe_load(text[4:end]) or {}
    except yaml.YAMLError:
        return {}, text
    return (data if isinstance(data, dict) else {}), text[end + 4:]


def _excerpt(body: str) -> str:
    for paragraph in re.split(r"\n\s*\n", body):
        value = " ".join(
            line.strip() for line in paragraph.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ).strip()
        if value:
            return value[:500]
    return ""


def _approved_persona(root: Path) -> list[dict[str, Any]]:
    for name in ("PROJECT_PERSONA.md", "project-persona.md"):
        path = root / "sdd" / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        meta, body = _frontmatter(text)
        if meta.get("status") != "approved":
            continue
        return [{
            "id": "persona:approved", "summary": redact(_excerpt(body)),
            "evidence": {"path": f"sdd/{name}", "sha256": _sha(path)},
        }]
    return []


def build(root: Path) -> dict[str, Any]:
    """Build L0→L3 memory with lossless links back to local sources."""
    atoms: list[dict[str, Any]] = []
    scenarios: dict[str, dict[str, Any]] = {}
    sources: list[dict[str, str]] = []
    specs = sorted(layout.specs_dir(root).glob("SPEC-*.md"))
    decisions = sorted(layout.decisions_dir(root).glob("*.md"))
    for path in [*specs, *decisions]:
        rel = path.relative_to(root).as_posix()
        sources.append({"path": rel, "sha256": _sha(path)})
    for path in specs:
        text = path.read_text(encoding="utf-8", errors="replace")
        meta, body = _frontmatter(text)
        spec_id = str(meta.get("spec") or path.stem.split("-", 2)[0])
        atom = {
            "id": f"atom:{spec_id}", "kind": "requirement",
            "title": str(meta.get("title") or spec_id),
            "summary": redact(_excerpt(body)), "status": str(meta.get("status", "unknown")),
            "evidence": {"path": path.relative_to(root).as_posix(), "sha256": _sha(path)},
        }
        atoms.append(atom)
        scenarios[spec_id] = {
            "id": f"scenario:{spec_id}", "title": atom["title"],
            "summary": atom["summary"], "atoms": [atom["id"]], "decisions": [],
        }
    for path in decisions:
        text = path.read_text(encoding="utf-8", errors="replace")
        ids = sorted(set(_SPEC.findall(text)))
        atom_id = f"atom:{path.stem}"
        atom = {
            "id": atom_id, "kind": "decision", "title": path.stem,
            "summary": redact(_excerpt(text)),
            "evidence": {"path": path.relative_to(root).as_posix(), "sha256": _sha(path)},
        }
        atoms.append(atom)
        for spec_id in ids:
            if spec_id in scenarios:
                scenarios[spec_id]["decisions"].append(atom_id)
    payload = {
        "schema": 1, "l0_sources": sources,
        "l1_atoms": sorted(atoms, key=lambda item: item["id"]),
        "l2_scenarios": [scenarios[key] for key in sorted(scenarios)],
        "l3_persona": _approved_persona(root),
    }
    destination = pyramid_path(root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return payload


def load(root: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(pyramid_path(root).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data if data.get("schema") == 1 else None


def _tokens(value: str) -> set[str]:
    return set(_TOKEN.findall(value.lower()))


def recall(
    root: Path, query: str, *, limit: int = 8,
    max_chars_per_item: int = 800, max_total_chars: int = 4_000,
) -> dict[str, Any]:
    """Fuse graph and pyramid ranks with RRF, then enforce hard budgets."""
    if limit <= 0 or max_chars_per_item <= 0 or max_total_chars <= 0:
        raise ValueError("recall limits must be positive")
    memory = load(root) or {"l1_atoms": [], "l2_scenarios": [], "l3_persona": []}
    query_tokens = _tokens(query)
    candidates: dict[str, dict[str, Any]] = {}
    lexical: list[tuple[str, float]] = []
    for level, key in ((1, "l1_atoms"), (2, "l2_scenarios"), (3, "l3_persona")):
        for item in memory.get(key, []):
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id", ""))
            text = " ".join(str(item.get(field, "")) for field in ("id", "title", "summary"))
            terms = _tokens(text)
            score = len(terms & query_tokens) / len(query_tokens) if query_tokens else 0.0
            if score:
                candidates[item_id] = {**item, "level": level, "source": "pyramid"}
                lexical.append((item_id, score))
    graph_hits = codegraph.search(root, query, limit=max(limit * 2, 10))
    for hit in graph_hits:
        candidates[hit.concept_id] = {
            "id": hit.concept_id, "title": hit.title, "summary": hit.summary,
            "evidence": {"path": hit.path}, "level": 1, "source": "graph",
        }
    ranks: list[list[str]] = [
        [item_id for item_id, _ in sorted(lexical, key=lambda row: (-row[1], row[0]))],
        [hit.concept_id for hit in graph_hits],
        [item_id for item_id, item in sorted(candidates.items()) if int(item["level"]) >= 2],
    ]
    scores: dict[str, float] = defaultdict(float)
    for ranking in ranks:
        for rank, item_id in enumerate(ranking, 1):
            scores[item_id] += 1.0 / (60 + rank)
    ordered = sorted(scores, key=lambda item_id: (-scores[item_id], item_id))
    results: list[dict[str, Any]] = []
    used = 0
    for item_id in ordered:
        item = candidates[item_id]
        rendered = redact(json.dumps(item, sort_keys=True, ensure_ascii=False))[:max_chars_per_item]
        if used + len(rendered) > max_total_chars:
            continue
        results.append({**item, "rrf_score": round(scores[item_id], 6), "rendered": rendered})
        used += len(rendered)
        if len(results) >= limit:
            break
    return {
        "query": query, "results": results, "used_chars": used,
        "max_total_chars": max_total_chars,
        "truncated": len(results) < len(ordered), "fusion": "rrf",
    }


def _decision_learnings(path: Path) -> list[tuple[str, str]]:
    active = False
    output: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("## "):
            active = line.strip() == "## Learnings for future runs"
            continue
        if not active:
            continue
        match = _LEARNING.match(line.strip())
        if match:
            output.append((match.group(1).strip(), match.group(2)))
    return output


def propose_persona(
    root: Path, *, trigger_every_n: int = 5, minimum_repetitions: int = 2,
) -> dict[str, Any]:
    if trigger_every_n <= 0 or minimum_repetitions <= 0:
        raise ValueError("persona thresholds must be positive")
    records = sorted(layout.decisions_dir(root).glob("DR-*.md"))
    if len(records) < trigger_every_n:
        return {"created": False, "reason": "trigger_not_reached", "records": len(records)}
    occurrences: dict[str, list[tuple[Path, str, str]]] = defaultdict(list)
    for path in records:
        for text, cite in _decision_learnings(path):
            key = " ".join(text.lower().split())
            occurrences[key].append((path, text, cite))
    stable = [values for values in occurrences.values() if len(values) >= minimum_repetitions]
    if not stable:
        return {"created": False, "reason": "no_repeated_conventions", "records": len(records)}
    digest = hashlib.sha256(
        "\0".join(sorted(occurrences)).encode()
    ).hexdigest()[:12]
    destination = layout.proposals_dir(root) / f"project-persona-{digest}.md"
    lines = [
        "---", "kind: project_persona", "status: proposed",
        f"source_count: {len(records)}", "approval: required", "---", "",
        "# Project Persona Proposal", "",
        "This is a proposal. It has no effect until reviewed and promoted to ",
        "`sdd/PROJECT_PERSONA.md` with `status: approved`.", "",
        "## Stable conventions", "",
    ]
    for values in sorted(stable, key=lambda group: group[0][1].lower()):
        lines.append(f"- {redact(values[0][1])}")
        for path, _text, cite in values:
            lines.append(f"  - evidence: `{path.relative_to(root)}` [{cite}]")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"created": True, "path": str(destination), "conventions": len(stable)}


def _action_signature(event: dict[str, Any]) -> str:
    summary = " ".join(str(event.get("summary", "")).lower().split())
    head = summary.split(" ", 1)[0][:40] if summary else "action"
    return f"{event.get('kind')}:{head}"


def propose_skills(
    root: Path, *, minimum_runs: int = 3, window: int = 3,
) -> list[dict[str, Any]]:
    if minimum_runs < 2 or window < 2:
        raise ValueError("skill thresholds require at least two runs/actions")
    patterns: dict[tuple[str, ...], list[tuple[str, int, int, list[str]]]] = defaultdict(list)
    base = flight.runs_dir(root)
    for run_dir in sorted(base.iterdir()) if base.is_dir() else []:
        try:
            actions = [event for event in flight.read_trace(root, run_dir.name) if event["kind"] in {"tool_use", "tool_result", "error", "retry"}]
        except (FileNotFoundError, ImportError, ValueError):
            continue
        seen: set[tuple[str, ...]] = set()
        for index in range(0, len(actions) - window + 1):
            chunk = actions[index:index + window]
            signature = tuple(_action_signature(event) for event in chunk)
            if signature in seen:
                continue
            seen.add(signature)
            patterns[signature].append((
                run_dir.name, int(chunk[0]["seq"]), int(chunk[-1]["seq"]),
                [str(event["summary"]) for event in chunk],
            ))
    proposals: list[dict[str, Any]] = []
    for signature, examples in sorted(patterns.items()):
        if len({item[0] for item in examples}) < minimum_runs:
            continue
        digest = hashlib.sha256("\0".join(signature).encode()).hexdigest()[:12]
        destination = layout.proposals_dir(root) / f"skill-{digest}.md"
        lines = [
            "---", "kind: skill", "status: proposed", "approval: required",
            f"observed_runs: {len(examples)}", "---", "",
            f"# Reusable Skill Proposal {digest}", "",
            "This artifact is evidence-backed but inert until HITL approval.", "",
            "## Trigger boundary", "", f"Recurring action sequence: `{' → '.join(signature)}`", "",
            "## Proposed steps", "",
        ]
        for index, value in enumerate(signature, 1):
            lines.append(f"{index}. `{value}`")
        lines += ["", "## Trace evidence", ""]
        for run_ref, lo, hi, summaries in examples:
            lines.append(f"- `{run_ref}` [e#{lo}:e#{hi}]")
            for summary in summaries:
                lines.append(f"  - {redact(summary)}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
        proposals.append({"path": str(destination), "pattern": list(signature), "runs": len(examples)})
    return proposals

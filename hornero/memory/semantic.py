"""Deterministic semantic projection over repository artifacts."""

from __future__ import annotations

import ast
import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Sequence
from typing import Any, Iterable, Protocol

import yaml


class PageLike(Protocol):
    concept_id: str
    path: str
    title: str
    category: str
    summary: str
    sha256: str
    imports: tuple[str, ...]


@dataclass(frozen=True)
class Entity:
    entity_id: str
    kind: str
    title: str
    summary: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Relation:
    src: str
    dst: str
    rel: str
    evidence: str = ""

    @property
    def relation_id(self) -> str:
        raw = f"{self.src}\0{self.dst}\0{self.rel}".encode()
        return "relation:" + hashlib.sha256(raw).hexdigest()[:20]


@dataclass(frozen=True)
class Provenance:
    subject_id: str
    subject_kind: str
    source_path: str
    source_hash: str
    origin: str
    generator: str = "hornero.semantic.v1"
    confidence: float = 1.0
    locator: str = ""


@dataclass
class SemanticBuild:
    entities: list[Entity] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    provenance: list[Provenance] = field(default_factory=list)


_SPEC = re.compile(r"\bSPEC-\d+\b")
_TASK = re.compile(r"\bTASK-\d+\b")
_PATH = re.compile(r"`([^`]+(?:\.py|\.js|\.ts|\.go|\.rs|\.md|\.yml|\.yaml))`")


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


def _add_entity(
    build: SemanticBuild,
    entity: Entity,
    *,
    source_path: str,
    source_hash: str,
    origin: str,
    locator: str = "",
    confidence: float = 1.0,
) -> None:
    build.entities.append(entity)
    build.provenance.append(Provenance(
        entity.entity_id, "entity", source_path, source_hash, origin,
        confidence=confidence, locator=locator,
    ))


def _add_relation(
    build: SemanticBuild,
    relation: Relation,
    *,
    source_path: str,
    source_hash: str,
    origin: str,
    confidence: float = 1.0,
) -> None:
    build.relations.append(relation)
    build.provenance.append(Provenance(
        relation.relation_id, "relation", source_path, source_hash, origin,
        confidence=confidence, locator=relation.evidence,
    ))


def _sha(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _row_hash(row: sqlite3.Row) -> str:
    payload = json.dumps(dict(row), sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def _module_index(pages: Iterable[PageLike]) -> dict[str, str]:
    result: dict[str, str] = {}
    for page in pages:
        path = Path(page.path)
        if path.suffix not in (".py", ".pyi"):
            continue
        parts = list(path.parts)
        if parts and parts[0] == "src":
            parts = parts[1:]
        parts[-1] = path.stem
        if parts[-1] == "__init__":
            parts.pop()
        if parts:
            result[".".join(parts)] = page.concept_id
    return result


def _parse_spec(root: Path, page: PageLike, build: SemanticBuild) -> None:
    path = root / page.path
    text = path.read_text(encoding="utf-8", errors="replace")
    meta, body = _frontmatter(text)
    spec_id = str(meta.get("spec") or "")
    if not _SPEC.fullmatch(spec_id):
        return
    requirement_id = f"requirement:{spec_id}"
    _add_entity(build, Entity(
        requirement_id, "requirement", str(meta.get("title") or spec_id),
        " ".join(body.strip().split())[:300],
        {"status": meta.get("status"), "kind": meta.get("kind")},
    ), source_path=page.path, source_hash=page.sha256, origin="spec")
    _add_relation(build, Relation(
        requirement_id, page.concept_id, "defined_in", "frontmatter.spec"
    ), source_path=page.path, source_hash=page.sha256, origin="spec")

    for source in meta.get("sources", []) or []:
        source_id = f"source:{source}"
        _add_entity(build, Entity(
            source_id, "source", str(source), "Requirement source signal",
            {"signal_id": str(source)},
        ), source_path=page.path, source_hash=page.sha256, origin="signal-reference")
        _add_relation(build, Relation(
            source_id, requirement_id, "supports", "frontmatter.sources"
        ), source_path=page.path, source_hash=page.sha256, origin="spec")

    for dependency in meta.get("depends_on", []) or []:
        dependency_id = str(dependency)
        if _SPEC.fullmatch(dependency_id):
            _add_relation(build, Relation(
                requirement_id, f"requirement:{dependency_id}", "depends_on",
                "frontmatter.depends_on",
            ), source_path=page.path, source_hash=page.sha256, origin="spec")

    for superseded in meta.get("supersedes", []) or []:
        superseded_id = str(superseded)
        if _SPEC.fullmatch(superseded_id):
            _add_relation(build, Relation(
                requirement_id, f"requirement:{superseded_id}", "supersedes",
                "frontmatter.supersedes",
            ), source_path=page.path, source_hash=page.sha256, origin="spec")

    for index, raw in enumerate(meta.get("acceptance_criteria", []) or [], start=1):
        criterion = str(raw)
        digest = hashlib.sha256(criterion.encode()).hexdigest()[:12]
        criterion_id = f"criterion:{spec_id}:{digest}"
        _add_entity(build, Entity(
            criterion_id, "criterion", f"{spec_id} criterion {index}", criterion,
            {"position": index},
        ), source_path=page.path, source_hash=page.sha256, origin="spec",
            locator=f"acceptance_criteria[{index - 1}]")
        _add_relation(build, Relation(
            requirement_id, criterion_id, "has_criterion",
            f"acceptance_criteria[{index - 1}]",
        ), source_path=page.path, source_hash=page.sha256, origin="spec")
        head = criterion.split(maxsplit=1)[0] if criterion.split() else "manual"
        control_id = f"control:quality:{head}"
        _add_entity(build, Entity(
            control_id, "control", head, f"Quality control executed by {head}",
            {"family": "quality"},
        ), source_path=page.path, source_hash=page.sha256, origin="criterion")
        _add_relation(build, Relation(
            criterion_id, control_id, "enforced_by", criterion
        ), source_path=page.path, source_hash=page.sha256, origin="criterion")


def _parse_task_index(root: Path, page: PageLike, build: SemanticBuild) -> None:
    try:
        data = json.loads((root / page.path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    tasks = data.get("tasks", []) if isinstance(data, dict) else []
    if not isinstance(tasks, list):
        return
    default_spec = str(data.get("feature_id") or "")
    for raw in tasks:
        if not isinstance(raw, dict):
            continue
        task_id = str(raw.get("id") or "")
        if not _TASK.fullmatch(task_id):
            continue
        entity_id = f"task:{task_id}"
        _add_entity(build, Entity(
            entity_id, "task", str(raw.get("title") or task_id),
            str(raw.get("status") or "pending"), raw,
        ), source_path=page.path, source_hash=page.sha256, origin="task-index")
        spec_id = str(raw.get("feature_id") or default_spec)
        if _SPEC.fullmatch(spec_id):
            _add_relation(build, Relation(
                f"requirement:{spec_id}", entity_id, "implemented_by", task_id
            ), source_path=page.path, source_hash=page.sha256, origin="task-index")
        files = raw.get("files", [])
        if isinstance(files, dict):
            files = list(files)
        if isinstance(files, list):
            for rel in files:
                if isinstance(rel, str) and (root / rel).is_file():
                    _add_relation(build, Relation(
                        entity_id, f"file:{rel}", "changes", rel
                    ), source_path=page.path, source_hash=page.sha256,
                        origin="task-index")


def _parse_decision(root: Path, page: PageLike, build: SemanticBuild) -> None:
    text = (root / page.path).read_text(encoding="utf-8", errors="replace")
    decision_id = f"decision:{Path(page.path).stem}"
    _add_entity(build, Entity(
        decision_id, "decision", Path(page.path).stem, page.summary,
        {"path": page.path},
    ), source_path=page.path, source_hash=page.sha256, origin="decision")
    for spec_id in sorted(set(_SPEC.findall(text))):
        _add_relation(build, Relation(
            f"requirement:{spec_id}", decision_id, "decided_by", spec_id
        ), source_path=page.path, source_hash=page.sha256, origin="decision")


def _parse_finding(root: Path, page: PageLike, build: SemanticBuild) -> None:
    text = (root / page.path).read_text(encoding="utf-8", errors="replace")
    meta, body = _frontmatter(text)
    finding_id = str(meta.get("finding") or "")
    if not finding_id.startswith("FIND-"):
        return
    entity_id = f"finding:{finding_id}"
    _add_entity(build, Entity(
        entity_id, "finding", finding_id,
        " ".join(body.strip().split())[:300],
        {
            "rule": meta.get("rule"), "category": meta.get("category"),
            "severity": meta.get("severity"), "risk": meta.get("risk"),
            "status": meta.get("status"), "confidence": meta.get("confidence"),
        },
    ), source_path=page.path, source_hash=page.sha256, origin="policy-pack")
    subject = str(meta.get("subject") or "").split(":L", 1)[0]
    if (root / subject).is_file():
        _add_relation(build, Relation(
            entity_id, f"file:{subject}", "affects", subject
        ), source_path=page.path, source_hash=page.sha256, origin="policy-pack")


def _parse_python_symbols(root: Path, page: PageLike, build: SemanticBuild) -> None:
    try:
        tree = ast.parse((root / page.path).read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeError):
        return
    for node in tree.body:
        if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        kind = "test" if node.name.startswith("test_") else "symbol"
        entity_id = f"{kind}:{page.path}:{node.name}"
        _add_entity(build, Entity(
            entity_id, kind, node.name,
            (ast.get_docstring(node) or "").split("\n", 1)[0],
            {"line": node.lineno, "file": page.path},
        ), source_path=page.path, source_hash=page.sha256, origin="python-ast",
            locator=f"L{node.lineno}")
        _add_relation(build, Relation(
            page.concept_id, entity_id, "declares", f"L{node.lineno}"
        ), source_path=page.path, source_hash=page.sha256, origin="python-ast")


def _parse_ledger(root: Path, build: SemanticBuild) -> None:
    path = root / ".hornero" / "ledger.db"
    if not path.is_file():
        return
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        runs = conn.execute(
            "SELECT run_id, command, started_at, finished_at, dry_run "
            "FROM runs ORDER BY run_id"
        ).fetchall()
        agent_runs = conn.execute(
            "SELECT run_ref, spec_id, task_id, actor, status, trace_path, "
            "started_at, finished_at FROM agent_runs ORDER BY run_ref"
        ).fetchall()
        improvements = conn.execute(
            "SELECT id, run_id, finding_id, status, branch, created_at "
            "FROM improvement_runs ORDER BY id"
        ).fetchall()
        runtime_events = conn.execute(
            "SELECT event_id, action, risk, cost_units, status, attempts, "
            "created_at, approved_by FROM runtime_events ORDER BY event_id"
        ).fetchall()
        runtime_feedback = conn.execute(
            "SELECT id, finding_id, rule_id, rating, notes, created_at "
            "FROM runtime_feedback ORDER BY id"
        ).fetchall()
        advisory_runs = conn.execute(
            "SELECT run_id, spec_id, mode, status, brief_hash, request_json, "
            "result_json, artifact_path, created_at FROM advisory_runs "
            "ORDER BY run_id"
        ).fetchall()
        advisory_findings = conn.execute(
            "SELECT finding_id, run_id, provider, summary, severity, "
            "disposition, reason, payload_json FROM advisory_findings "
            "ORDER BY finding_id"
        ).fetchall()
        mockup_runs = conn.execute(
            "SELECT run_id, spec_id, status, provider, parent_run_id, "
            "manifest_path, request_json, result_json, created_at "
            "FROM mockup_runs ORDER BY run_id"
        ).fetchall()
        visual_artifacts = conn.execute(
            "SELECT artifact_id, run_id, view_name, path, sha256, media_type, "
            "width, height, bytes, promoted_path FROM visual_artifacts "
            "ORDER BY artifact_id"
        ).fetchall()
    except sqlite3.DatabaseError:
        return
    finally:
        if "conn" in locals():
            conn.close()
    for row in runs:
        run_id = str(row["run_id"])
        _add_entity(build, Entity(
            f"run:{run_id}", "run", run_id, str(row["command"]),
            {
                "command": row["command"], "started_at": row["started_at"],
                "finished_at": row["finished_at"], "dry_run": bool(row["dry_run"]),
            },
        ), source_path=".hornero/ledger.db", source_hash=_row_hash(row),
            origin="ledger", locator=f"runs:{run_id}")
    for row in agent_runs:
        run_ref = str(row["run_ref"])
        entity_id = f"agent_run:{run_ref}"
        _add_entity(build, Entity(
            entity_id, "agent_run", run_ref, str(row["status"]), dict(row),
        ), source_path=".hornero/ledger.db", source_hash=_row_hash(row),
            origin="ledger", locator=f"agent_runs:{run_ref}")
        if row["spec_id"]:
            _add_relation(build, Relation(
                f"requirement:{row['spec_id']}", entity_id, "built_by", run_ref
            ), source_path=".hornero/ledger.db", source_hash=_row_hash(row),
                origin="ledger")
        if row["task_id"]:
            _add_relation(build, Relation(
                f"task:{row['task_id']}", entity_id, "executed_by", run_ref
            ), source_path=".hornero/ledger.db", source_hash=_row_hash(row),
                origin="ledger")
    for row in improvements:
        run_id = str(row["run_id"])
        finding_id = f"finding:{row['finding_id']}"
        _add_relation(build, Relation(
            finding_id, f"run:{run_id}", "attempted_in", str(row["status"])
        ), source_path=".hornero/ledger.db", source_hash=_row_hash(row),
            origin="ledger")
    for row in runtime_events:
        event_id = f"runtime_event:{row['event_id']}"
        _add_entity(build, Entity(
            event_id, "runtime_event", str(row["event_id"]), str(row["status"]),
            dict(row),
        ), source_path=".hornero/ledger.db", source_hash=_row_hash(row),
            origin="runtime-ledger", locator=f"runtime_events:{row['event_id']}")
    for row in runtime_feedback:
        feedback_id = f"feedback:{row['id']}"
        _add_entity(build, Entity(
            feedback_id, "feedback", f"Feedback {row['id']}", str(row["notes"]),
            dict(row),
        ), source_path=".hornero/ledger.db", source_hash=_row_hash(row),
            origin="runtime-ledger", locator=f"runtime_feedback:{row['id']}")
        _add_relation(build, Relation(
            f"finding:{row['finding_id']}", feedback_id, "evaluated_by",
            f"rating={row['rating']}",
        ), source_path=".hornero/ledger.db", source_hash=_row_hash(row),
            origin="runtime-ledger")
    for row in advisory_runs:
        run_id = str(row["run_id"])
        entity_id = f"advisory_run:{run_id}"
        result = json.loads(row["result_json"])
        request = json.loads(row["request_json"])
        _add_entity(build, Entity(
            entity_id, "advisory_run", run_id, str(row["status"]),
            {
                "spec_id": row["spec_id"], "mode": row["mode"],
                "status": row["status"], "brief_hash": row["brief_hash"],
                "artifact_path": row["artifact_path"],
            },
        ), source_path=".hornero/ledger.db", source_hash=_row_hash(row),
            origin="advisory-ledger", locator=f"advisory_runs:{run_id}")
        _add_relation(build, Relation(
            f"requirement:{row['spec_id']}", entity_id, "requested",
            str(row["mode"]),
        ), source_path=".hornero/ledger.db", source_hash=_row_hash(row),
            origin="advisory-ledger")
        for index, evidence in enumerate(request.get("evidence", []), start=1):
            if not isinstance(evidence, dict):
                continue
            digest = str(evidence.get("sha256") or "")[:20]
            evidence_id = f"advisory_evidence:{run_id}:{digest or index}"
            _add_entity(build, Entity(
                evidence_id, "evidence",
                str(evidence.get("locator") or f"Evidence {index}"),
                str(evidence.get("content") or "")[:300],
                {"sha256": evidence.get("sha256"), "locator": evidence.get("locator")},
            ), source_path=".hornero/ledger.db", source_hash=_row_hash(row),
                origin="advisory-ledger")
            _add_relation(build, Relation(
                entity_id, evidence_id, "grounded_by",
                str(evidence.get("locator") or ""),
            ), source_path=".hornero/ledger.db", source_hash=_row_hash(row),
                origin="advisory-ledger")
        for provider in result.get("provider_runs", []):
            if not isinstance(provider, dict):
                continue
            provider_name = str(provider.get("provider") or "unknown")
            provider_id = f"provider_run:{run_id}:{provider_name}"
            _add_entity(build, Entity(
                provider_id, "provider_run", provider_name,
                str(provider.get("status") or ""),
                provider,
            ), source_path=".hornero/ledger.db", source_hash=_row_hash(row),
                origin="advisory-ledger")
            _add_relation(build, Relation(
                entity_id, provider_id, "has_perspective", provider_name,
            ), source_path=".hornero/ledger.db", source_hash=_row_hash(row),
                origin="advisory-ledger")
        synthesis = result.get("synthesis")
        if isinstance(synthesis, dict) and row["status"] == "completed":
            synthesis_id = f"advisory_synthesis:{run_id}"
            _add_entity(build, Entity(
                synthesis_id, "synthesis", f"Synthesis {run_id}",
                str(synthesis.get("summary") or ""), synthesis,
            ), source_path=".hornero/ledger.db", source_hash=_row_hash(row),
                origin="advisory-ledger")
            _add_relation(build, Relation(
                entity_id, synthesis_id, "summarized_by", run_id,
            ), source_path=".hornero/ledger.db", source_hash=_row_hash(row),
                origin="advisory-ledger")
    for row in advisory_findings:
        finding_id = f"advisory_finding:{row['finding_id']}"
        payload = json.loads(row["payload_json"])
        _add_entity(build, Entity(
            finding_id, "advisory_finding", str(row["finding_id"]),
            str(row["summary"]), payload,
        ), source_path=".hornero/ledger.db", source_hash=_row_hash(row),
            origin="advisory-ledger")
        provider_id = f"provider_run:{row['run_id']}:{row['provider']}"
        _add_relation(build, Relation(
            provider_id, finding_id, "reported", str(row["severity"]),
        ), source_path=".hornero/ledger.db", source_hash=_row_hash(row),
            origin="advisory-ledger")
        disposition_id = f"disposition:{row['run_id']}:{row['finding_id']}"
        _add_entity(build, Entity(
            disposition_id, "disposition", str(row["disposition"]),
            str(row["reason"]),
            {"disposition": row["disposition"], "reason": row["reason"]},
        ), source_path=".hornero/ledger.db", source_hash=_row_hash(row),
            origin="advisory-ledger")
        _add_relation(build, Relation(
            finding_id, disposition_id, "disposed_as", str(row["reason"]),
        ), source_path=".hornero/ledger.db", source_hash=_row_hash(row),
            origin="advisory-ledger")
    for row in mockup_runs:
        run_id = str(row["run_id"])
        entity_id = f"mockup_run:{run_id}"
        result = json.loads(row["result_json"])
        _add_entity(build, Entity(
            entity_id, "mockup_run", run_id, str(row["status"]),
            {
                "provider": row["provider"], "manifest_path": row["manifest_path"],
                "parent_run_id": row["parent_run_id"], "status": row["status"],
            },
        ), source_path=".hornero/ledger.db", source_hash=_row_hash(row),
            origin="mockup-ledger", locator=f"mockup_runs:{run_id}")
        _add_relation(build, Relation(
            f"requirement:{row['spec_id']}", entity_id, "requested", "mockup",
        ), source_path=".hornero/ledger.db", source_hash=_row_hash(row),
            origin="mockup-ledger")
        provider_id = f"provider_run:{run_id}:{row['provider']}"
        _add_entity(build, Entity(
            provider_id, "provider_run", str(row["provider"]),
            str(row["status"]), {"session_id": result.get("session_id")},
        ), source_path=".hornero/ledger.db", source_hash=_row_hash(row),
            origin="mockup-ledger")
        _add_relation(build, Relation(
            entity_id, provider_id, "produced_by", str(row["provider"]),
        ), source_path=".hornero/ledger.db", source_hash=_row_hash(row),
            origin="mockup-ledger")
        reference = result.get("reference")
        if isinstance(reference, dict) and reference.get("sha256"):
            reference_id = f"reference_image:{str(reference['sha256'])[:20]}"
            _add_entity(build, Entity(
                reference_id, "reference_image", "Reference image",
                str(reference.get("source_path") or ""), reference,
            ), source_path=".hornero/ledger.db", source_hash=_row_hash(row),
                origin="mockup-ledger")
            _add_relation(build, Relation(
                entity_id, reference_id, "uses_reference",
                str(reference.get("source_path") or ""),
            ), source_path=".hornero/ledger.db", source_hash=_row_hash(row),
                origin="mockup-ledger")
        if row["parent_run_id"]:
            _add_relation(build, Relation(
                entity_id, f"mockup_run:{row['parent_run_id']}", "refines",
                str(row["parent_run_id"]),
            ), source_path=".hornero/ledger.db", source_hash=_row_hash(row),
                origin="mockup-ledger")
    for row in visual_artifacts:
        artifact_id = f"visual_artifact:{row['artifact_id']}"
        _add_entity(build, Entity(
            artifact_id, "visual_artifact", str(row["view_name"]),
            str(row["path"]), dict(row),
        ), source_path=".hornero/ledger.db", source_hash=_row_hash(row),
            origin="mockup-ledger")
        _add_relation(build, Relation(
            f"mockup_run:{row['run_id']}", artifact_id, "produced",
            str(row["view_name"]),
        ), source_path=".hornero/ledger.db", source_hash=_row_hash(row),
            origin="mockup-ledger")
        if row["promoted_path"]:
            promoted_id = f"repository_artifact:{row['artifact_id']}"
            _add_entity(build, Entity(
                promoted_id, "repository_artifact", str(row["view_name"]),
                str(row["promoted_path"]), {"path": row["promoted_path"]},
            ), source_path=".hornero/ledger.db", source_hash=_row_hash(row),
                origin="mockup-ledger")
            _add_relation(build, Relation(
                artifact_id, promoted_id, "promoted_as",
                str(row["promoted_path"]),
            ), source_path=".hornero/ledger.db", source_hash=_row_hash(row),
                origin="mockup-ledger")


def derive(root: Path, pages: Sequence[Any]) -> SemanticBuild:
    build = SemanticBuild()
    module_index = _module_index(pages)
    for page in pages:
        if page.concept_id.startswith("dir:"):
            continue
        artifact_kind = "test_file" if page.path.startswith("tests/") else "artifact"
        _add_entity(build, Entity(
            page.concept_id, artifact_kind, page.title, page.summary,
            {"category": page.category, "path": page.path},
        ), source_path=page.path, source_hash=page.sha256, origin="repository")
        if page.path.startswith("sdd/specs/") and Path(page.path).name.startswith("SPEC-"):
            _parse_spec(root, page, build)
        if page.path.startswith("sdd/tasks/index/") and page.path.endswith(".json"):
            _parse_task_index(root, page, build)
        if page.path.startswith("sdd/decisions/") and Path(page.path).name.startswith(("ADR-", "DR-")):
            _parse_decision(root, page, build)
        if page.path.startswith("sdd/findings/") and Path(page.path).name.startswith("FIND-"):
            _parse_finding(root, page, build)
        if page.path.endswith((".py", ".pyi")):
            _parse_python_symbols(root, page, build)

    for page in pages:
        if not page.path.startswith("tests/"):
            continue
        for imported in page.imports:
            target = module_index.get(imported)
            if target:
                _add_relation(build, Relation(
                    target, page.concept_id, "verified_by", imported
                ), source_path=page.path, source_hash=page.sha256, origin="python-import")

    _parse_ledger(root, build)

    entities = {entity.entity_id: entity for entity in build.entities}
    build.entities = sorted(entities.values(), key=lambda item: item.entity_id)
    relations = {
        (relation.src, relation.dst, relation.rel): relation
        for relation in build.relations
        if relation.src in entities and relation.dst in entities
    }
    build.relations = sorted(
        relations.values(), key=lambda item: (item.src, item.dst, item.rel)
    )
    valid_subjects = set(entities) | {r.relation_id for r in build.relations}
    provenance = {
        (item.subject_id, item.source_path, item.source_hash): item
        for item in build.provenance
        if item.subject_id in valid_subjects
    }
    build.provenance = sorted(
        provenance.values(),
        key=lambda item: (item.subject_id, item.source_path, item.source_hash),
    )
    return build

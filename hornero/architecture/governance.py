"""Spec preflight, fitness checks, context packs and implementation deltas."""

from __future__ import annotations

import json
import subprocess
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from hornero import layout
from hornero.architecture.corpus import ArchitectureCorpus
from hornero.architecture.model import (
    ArchitectureDeclaration,
    ArchitectureError,
    ArchitectureFinding,
    ArchitectureRecord,
    ArchitectureReport,
)
from hornero.architecture.protocol import seal_context
from hornero.lifecycle import SpecCorpus, SpecDoc


def _list(value: object, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ArchitectureError(f"spec architecture.{field} must be a string list")
    return tuple(value)


def declaration_from_spec(doc: SpecDoc) -> ArchitectureDeclaration | None:
    try:
        meta = yaml.safe_load(doc.raw_frontmatter) or {}
    except yaml.YAMLError as exc:
        raise ArchitectureError(f"{doc.path}: invalid frontmatter: {exc}") from exc
    raw = meta.get("architecture")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ArchitectureError(f"{doc.path}: architecture must be a mapping")
    allowed = {
        "profiles", "domains", "requests", "reuses", "extends", "introduces",
        "decisions", "quality_budgets",
    }
    unknown = set(raw) - allowed
    if unknown:
        raise ArchitectureError(
            f"{doc.path}: unknown architecture keys: {sorted(unknown)}"
        )
    budgets = raw.get("quality_budgets") or {}
    if not isinstance(budgets, dict):
        raise ArchitectureError(
            f"{doc.path}: architecture.quality_budgets must be a mapping"
        )
    if not all(
        isinstance(key, str)
        and isinstance(value, (str, int, float))
        and not isinstance(value, bool)
        for key, value in budgets.items()
    ):
        raise ArchitectureError(
            f"{doc.path}: quality budget values must be strings or numbers"
        )
    return ArchitectureDeclaration(
        profiles=_list(raw.get("profiles"), "profiles"),
        domains=_list(raw.get("domains"), "domains"),
        requests=_list(raw.get("requests"), "requests"),
        reuses=_list(raw.get("reuses"), "reuses"),
        extends=_list(raw.get("extends"), "extends"),
        introduces=_list(raw.get("introduces"), "introduces"),
        decisions=_list(raw.get("decisions"), "decisions"),
        quality_budgets=dict(budgets),
    )


def _severity(corpus: ArchitectureCorpus, *, legacy: bool = False) -> str:
    assert corpus.project is not None
    if legacy:
        return {
            "ignore": "info", "warn": "warning", "block": "blocking"
        }[corpus.project.legacy_policy]
    if corpus.project.governance_mode == "off":
        return "info"
    return "blocking" if corpus.project.governance_mode == "enforced" else "warning"


def _finding(
    code: str,
    severity: str,
    subject: str,
    message: str,
    *,
    profile: str = "core",
    rule_id: str = "",
    evidence: tuple[str, ...] = (),
    remediation: str = "",
    exception_eligible: bool = False,
) -> ArchitectureFinding:
    return ArchitectureFinding(
        code, severity, subject, message, profile, rule_id, evidence,
        remediation, exception_eligible,
    )


def _active_exceptions(
    corpus: ArchitectureCorpus,
) -> tuple[dict[str, set[str]], list[ArchitectureFinding]]:
    waived: dict[str, set[str]] = {}
    findings: list[ArchitectureFinding] = []
    today = date.today().isoformat()
    for exception in corpus.list("exception"):
        raw = exception.raw
        required = (
            "owner", "reason", "scope", "approver", "created", "expires",
            "remediation",
        )
        missing = [field for field in required if not raw.get(field)]
        rule_id = str(raw.get("waives") or "")
        if missing or not rule_id:
            findings.append(_finding(
                "INVALID_EXCEPTION", "blocking", exception.record_id,
                "exception is missing: " + ", ".join((*missing, *(
                    ("waives",) if not rule_id else ()
                ))),
                rule_id="ARCH-EXCEPTION-001",
                evidence=(exception.path.as_posix(),),
            ))
            continue
        if str(raw["expires"]) < today:
            findings.append(_finding(
                "EXPIRED_EXCEPTION", "blocking", exception.record_id,
                f"exception expired on {raw['expires']}",
                rule_id=rule_id, evidence=(exception.path.as_posix(),),
            ))
            continue
        waived.setdefault(rule_id, set()).add(str(raw["scope"]))
    return waived, findings


def _waived(
    waived: dict[str, set[str]], rule_id: str, record: ArchitectureRecord
) -> bool:
    scopes = waived.get(rule_id, set())
    return bool(scopes & {
        "*", record.record_id, f"{record.kind}:{record.record_id}",
        record.graph_id,
    })


def _record_findings(corpus: ArchitectureCorpus) -> list[ArchitectureFinding]:
    assert corpus.project is not None
    findings: list[ArchitectureFinding] = []
    waived, exception_findings = _active_exceptions(corpus)
    findings.extend(exception_findings)
    for profile in corpus.unknown_profiles:
        findings.append(_finding(
            "UNKNOWN_PROFILE", "blocking", profile,
            "configured architecture profile is unavailable",
            remediation="Install or define the exact namespaced profile.",
        ))
    severity = _severity(corpus)
    for record in corpus.list():
        if record.kind in {"component", "interface", "domain", "deployment"}:
            if not record.owner and not _waived(
                waived, "ARCH-OWNER-001", record
            ):
                findings.append(_finding(
                    "MISSING_OWNER", severity, record.graph_id,
                    f"{record.kind} has no accountable owner",
                    rule_id="ARCH-OWNER-001",
                    evidence=(record.path.as_posix(),),
                    remediation="Set an explicit owner in the architecture record.",
                    exception_eligible=True,
                ))
        if record.kind in {"component", "interface"}:
            if not record.evidence and not _waived(
                waived, "ARCH-EVIDENCE-001", record
            ):
                findings.append(_finding(
                    "MISSING_EVIDENCE", severity, record.graph_id,
                    f"{record.kind} has no literal implementation evidence",
                    rule_id="ARCH-EVIDENCE-001",
                    evidence=(record.path.as_posix(),),
                    remediation="Link a repository path and optional locator.",
                    exception_eligible=True,
                ))
            for evidence in record.evidence:
                if not evidence.sha256:
                    findings.append(_finding(
                        "EVIDENCE_SOURCE_MISSING", severity, record.graph_id,
                        f"evidence path does not resolve: {evidence.path}",
                        rule_id="ARCH-EVIDENCE-001",
                        evidence=(record.path.as_posix(), evidence.path),
                        remediation="Restore the source or update the evidence locator.",
                        exception_eligible=True,
                    ))
        if record.kind == "interface" and "rest-service" in corpus.profiles:
            if not record.raw.get("contract"):
                findings.append(_finding(
                    "REST_INTERFACE_WITHOUT_CONTRACT", severity, record.graph_id,
                    "REST interface has no authoritative contract locator",
                    profile="rest-service", rule_id="ARCH-REST-CONTRACT-001",
                    evidence=(record.path.as_posix(),),
                    remediation="Declare contract.path and contract locator.",
                    exception_eligible=True,
                ))
        if record.kind == "component" and "background-worker" in corpus.profiles:
            lifecycle = record.raw.get("lifecycle")
            if not isinstance(lifecycle, dict) or not all(
                lifecycle.get(key) for key in ("retry", "idempotency", "shutdown")
            ):
                findings.append(_finding(
                    "WORKER_LIFECYCLE_INCOMPLETE", severity, record.graph_id,
                    "worker component must declare retry, idempotency, and shutdown",
                    profile="background-worker",
                    rule_id="ARCH-WORKER-LIFECYCLE-001",
                    evidence=(record.path.as_posix(),),
                    exception_eligible=True,
                ))
    return findings


def _preflight_findings(
    corpus: ArchitectureCorpus, doc: SpecDoc
) -> list[ArchitectureFinding]:
    assert corpus.project is not None
    declaration = declaration_from_spec(doc)
    if corpus.project.governance_mode == "off":
        return []
    if declaration is None:
        severity = _severity(corpus, legacy=True)
        if severity == "info":
            return []
        return [_finding(
            "SPEC_ARCHITECTURE_MISSING", severity, doc.spec_id,
            "spec has no architecture alignment declaration",
            remediation="Add the structured architecture frontmatter block.",
        )]
    findings: list[ArchitectureFinding] = []
    active_profiles = set(corpus.profiles)
    for profile in declaration.profiles:
        if profile not in active_profiles:
            findings.append(_finding(
                "SPEC_PROFILE_UNAVAILABLE", "blocking", doc.spec_id,
                f"spec requires unavailable profile {profile!r}",
            ))
    for domain in declaration.domains:
        if corpus.get(domain, "domain") is None:
            findings.append(_finding(
                "UNKNOWN_DOMAIN", _severity(corpus), doc.spec_id,
                f"architecture domain {domain!r} is not registered",
            ))
    chosen = set((
        *declaration.reuses, *declaration.extends, *declaration.introduces
    ))
    for capability in declaration.requests:
        result = corpus.resolve(capability)
        if result.resolution == "needs_human":
            findings.append(_finding(
                "REUSE_NEEDS_HUMAN", "blocking", f"{doc.spec_id}:{capability}",
                "; ".join(result.explanation),
                evidence=tuple(
                    evidence.path for item in (*result.candidates, *result.excluded)
                    for evidence in item.evidence
                ),
            ))
        elif result.resolution != "new_component" and result.selected not in chosen:
            findings.append(_finding(
                "REUSE_PLAN_MISMATCH", "blocking", f"{doc.spec_id}:{capability}",
                f"resolved provider {result.selected!r} is not declared in "
                "architecture.reuses or architecture.extends",
                remediation="Declare the selected provider or record a decision.",
            ))
        elif result.resolution == "new_component" and not declaration.introduces:
            findings.append(_finding(
                "NEW_COMPONENT_UNDECLARED", "blocking",
                f"{doc.spec_id}:{capability}",
                "no provider exists and the spec declares no introduced component",
            ))
    for component in declaration.reuses:
        if corpus.get(component, "component") is None:
            findings.append(_finding(
                "UNKNOWN_REUSE", "blocking", doc.spec_id,
                f"reused component {component!r} is not registered",
            ))
    for component in declaration.introduces:
        record = corpus.get(component, "component")
        if record is None:
            findings.append(_finding(
                "INTRODUCED_COMPONENT_UNREGISTERED", _severity(corpus), doc.spec_id,
                f"introduced component {component!r} has no architecture record",
            ))
        elif not record.owner:
            findings.append(_finding(
                "INTRODUCED_COMPONENT_WITHOUT_OWNER", "blocking", doc.spec_id,
                f"introduced component {component!r} has no owner",
            ))
    for decision in declaration.decisions:
        if corpus.get(decision, "decision") is None and not (
            layout.decisions_dir(corpus.root) / f"{decision}.md"
        ).is_file():
            findings.append(_finding(
                "UNKNOWN_DECISION", _severity(corpus), doc.spec_id,
                f"decision {decision!r} cannot be resolved",
            ))
    return findings


def preflight_spec(root: Path, spec_id: str) -> ArchitectureReport:
    corpus = ArchitectureCorpus(root)
    specs = SpecCorpus(layout.specs_dir(root))
    doc = specs.by_id.get(spec_id)
    if doc is None:
        raise ArchitectureError(f"unknown spec: {spec_id}")
    findings = sorted(
        _preflight_findings(corpus, doc),
        key=lambda item: (item.severity, item.code, item.subject),
    )
    return ArchitectureReport(
        tuple(findings), (spec_id,), tuple(corpus.profiles)
    )


def check_architecture(
    root: Path, *, spec_id: str | None = None, all_specs: bool = False
) -> ArchitectureReport:
    corpus = ArchitectureCorpus(root)
    findings = _record_findings(corpus)
    checked: list[str] = []
    specs = SpecCorpus(layout.specs_dir(root))
    if spec_id:
        doc = specs.by_id.get(spec_id)
        if doc is None:
            raise ArchitectureError(f"unknown spec: {spec_id}")
        checked.append(spec_id)
        findings.extend(_preflight_findings(corpus, doc))
    elif all_specs:
        for doc in specs.docs:
            checked.append(doc.spec_id)
            findings.extend(_preflight_findings(corpus, doc))
    findings.sort(key=lambda item: (item.severity, item.code, item.subject))
    return ArchitectureReport(
        tuple(findings), tuple(checked), tuple(corpus.profiles)
    )


def _constraint_payload(record: ArchitectureRecord, root: Path) -> dict[str, Any]:
    quote = str(
        record.raw.get("statement")
        or record.raw.get("decision")
        or record.raw.get("title")
        or record.title
    )
    return {
        "id": record.record_id,
        "source": record.path.relative_to(root).as_posix(),
        "quote": quote,
        "sha256": record.sha256,
        "authority": record.authority.value,
    }


def build_context(root: Path, spec_id: str) -> dict[str, Any]:
    corpus = ArchitectureCorpus(root)
    specs = SpecCorpus(layout.specs_dir(root))
    doc = specs.by_id.get(spec_id)
    if doc is None:
        raise ArchitectureError(f"unknown spec: {spec_id}")
    declaration = declaration_from_spec(doc)
    if declaration is None:
        raise ArchitectureError(f"{spec_id}: architecture declaration is missing")
    resolutions = [corpus.resolve(capability) for capability in declaration.requests]
    candidates = [
        {
            "capability": result.capability,
            "component": item.component,
            "resolution": item.resolution,
            "evidence": [
                {
                    **evidence.to_dict(),
                    "content_hash": evidence.sha256,
                }
                for evidence in item.evidence
            ],
        }
        for result in resolutions
        for item in result.candidates
    ]
    constraints = [
        _constraint_payload(record, root)
        for kind in ("constraint", "decision")
        for record in corpus.list(kind)
    ]
    payload: dict[str, Any] = {
        "schema": "hornero.architecture.context/v1",
        "project": {
            "id": corpus.project.project_id if corpus.project else "",
            "profiles": list(corpus.profiles),
        },
        "spec_id": spec_id,
        "requested_capabilities": list(declaration.requests),
        "reuse_candidates": candidates,
        "constraints": constraints,
        "forbidden_duplications": sorted({
            result.capability for result in resolutions if result.candidates
        }),
        "quality_budgets": declaration.quality_budgets,
        "unknowns": [
            result.capability for result in resolutions
            if result.resolution == "needs_human"
        ],
    }
    return seal_context(payload)


def architecture_diff(
    root: Path,
    *,
    spec_id: str | None = None,
    git_ref: str | None = None,
    commit: bool = False,
) -> dict[str, Any]:
    """Compare a spec plan with records, optionally scoped by changed paths."""
    corpus = ArchitectureCorpus(root)
    changed: list[str] = []
    if git_ref:
        try:
            argv = (
                ["git", "-C", str(root), "show", "--format=", "--name-only", git_ref]
                if commit
                else ["git", "-C", str(root), "diff", "--name-only", git_ref, "--"]
            )
            proc = subprocess.run(
                argv,
                capture_output=True, text=True, check=True, timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ArchitectureError(f"cannot diff {git_ref!r}: {exc}") from exc
        changed = sorted(filter(None, proc.stdout.splitlines()))
    reused: list[str] = []
    extended: list[str] = []
    introduced: list[str] = []
    deviations: list[dict[str, str]] = []
    if spec_id:
        specs = SpecCorpus(layout.specs_dir(root))
        doc = specs.by_id.get(spec_id)
        if doc is None:
            raise ArchitectureError(f"unknown spec: {spec_id}")
        declaration = declaration_from_spec(doc)
        if declaration is None:
            raise ArchitectureError(f"{spec_id}: architecture declaration is missing")
        reused = list(declaration.reuses)
        extended = list(declaration.extends)
        introduced = list(declaration.introduces)
        for item in (*declaration.reuses, *declaration.extends):
            if corpus.get(item, "component") is None:
                deviations.append({
                    "entity": item,
                    "kind": "missing",
                    "message": "planned component is absent from architecture corpus",
                })
        for item in declaration.introduces:
            if corpus.get(item, "component") is None:
                deviations.append({
                    "entity": item,
                    "kind": "unregistered",
                    "message": "introduced component has no architecture record",
                })
    architecture_prefix = corpus.architecture_dir.relative_to(root).as_posix() + "/"
    return {
        "schema": "hornero.architecture.delta/v1",
        "spec_id": spec_id,
        "git_ref": git_ref,
        "git_ref_kind": "commit" if commit and git_ref else (
            "base" if git_ref else None
        ),
        "changed_architecture_files": [
            path for path in changed if path.startswith(architecture_prefix)
        ],
        "reused": reused,
        "extended": extended,
        "introduced": introduced,
        "deviations": deviations,
    }


def dump_report(report: ArchitectureReport) -> str:
    return json.dumps(report.to_dict(), indent=2, sort_keys=True)

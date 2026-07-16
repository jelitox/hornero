"""Offline supply-chain, threat-model and compliance evidence engines."""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from hornero import layout


class AssuranceError(RuntimeError):
    pass


@dataclass(frozen=True)
class AssuranceIssue:
    issue_id: str
    rule_id: str
    category: str
    severity: str
    risk: str
    title: str
    description: str
    subject: str
    remediation: str
    evidence: str = ""


def _issue(
    rule_id: str, category: str, severity: str, risk: str, title: str,
    description: str, subject: str, remediation: str, evidence: str = "",
) -> AssuranceIssue:
    digest = hashlib.sha256(f"{rule_id}\0{subject}".encode()).hexdigest()[:12]
    return AssuranceIssue(
        f"ASSURE-{digest}", rule_id, category, severity, risk, title,
        description, subject, remediation, evidence,
    )


_DEP = re.compile(r"^([A-Za-z0-9_.-]+)\s*(.*)$")


def supply_chain(
    root: Path, *, vulnerability_feed: Path | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    path = root / "pyproject.toml"
    try:
        project = tomllib.loads(path.read_text(encoding="utf-8")).get("project", {})
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise AssuranceError(f"cannot parse pyproject.toml: {exc}") from exc
    dependencies = project.get("dependencies", [])
    if not isinstance(dependencies, list):
        raise AssuranceError("project.dependencies must be a list")
    components: list[dict[str, Any]] = []
    issues: list[AssuranceIssue] = []
    for raw in sorted(map(str, dependencies)):
        match = _DEP.match(raw)
        if not match:
            continue
        name, constraint = match.groups()
        components.append({
            "type": "library", "name": name.lower(),
            "version_constraint": constraint or None,
            "purl": f"pkg:pypi/{name.lower()}",
        })
        if not constraint:
            issues.append(_issue(
                "SC001", "supply_chain", "medium", "low",
                "Dependency has no version constraint", raw, "pyproject.toml",
                "Add tested lower and upper compatibility bounds.", raw,
            ))
    license_value = project.get("license")
    if not license_value:
        issues.append(_issue(
            "SC002", "supply_chain", "medium", "low",
            "Project license metadata is missing",
            "pyproject.toml does not declare project.license.", "pyproject.toml",
            "Declare an SPDX-compatible project license.",
        ))
    vulnerabilities: list[dict[str, Any]] = []
    if vulnerability_feed is not None:
        try:
            feed = json.loads(vulnerability_feed.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AssuranceError(f"invalid vulnerability feed: {exc}") from exc
        if feed.get("schema") != 1 or not isinstance(feed.get("vulnerabilities"), list):
            raise AssuranceError("vulnerability feed must use schema 1")
        by_name = {item["name"]: item for item in components}
        for vulnerability in feed["vulnerabilities"]:
            if not isinstance(vulnerability, dict):
                continue
            package = str(vulnerability.get("package", "")).lower()
            component = by_name.get(package)
            if component is None:
                continue
            affected = list(map(str, vulnerability.get("versions", [])))
            constraint = str(component.get("version_constraint") or "")
            exact = constraint.removeprefix("==") if constraint.startswith("==") else ""
            if affected and exact and exact not in affected:
                continue
            vulnerabilities.append(vulnerability)
            severity = str(vulnerability.get("severity", "high")).lower()
            severity = severity if severity in ("critical", "high", "medium", "low") else "high"
            issues.append(_issue(
                "SC003", "supply_chain", severity, "high",
                f"Known vulnerability {vulnerability.get('id', 'unknown')}",
                f"{package} matches the supplied offline vulnerability feed.",
                f"dependency:{package}",
                "Upgrade to a non-affected version and run all gates.",
                json.dumps(vulnerability, sort_keys=True),
            ))
    sbom = {
        "bomFormat": "CycloneDX", "specVersion": "1.5", "version": 1,
        "metadata": {"component": {
            "type": "application", "name": str(project.get("name", root.name)),
            "version": str(project.get("version", "0.0.0")),
            "license": license_value,
        }},
        "components": components, "vulnerabilities": vulnerabilities,
    }
    result = {"sbom": sbom, "issues": [asdict(item) for item in issues]}
    if persist:
        output = layout.reports_dir(root) / "sbom.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def threat_model(root: Path, *, persist: bool = True) -> dict[str, Any]:
    components: set[str] = set()
    lock = root / ".hornero" / "blueprint.lock"
    if lock.is_file():
        try:
            components = set(json.loads(lock.read_text())["components"])
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
    controls = set(components)
    from hornero.blueprints import COMPONENTS

    for name in components:
        component = COMPONENTS.get(name)
        if component:
            controls.update(component.provides)
    if (root / "migrations").is_dir():
        controls.add("migrations")
    if list(root.glob("src/*/auth.py")):
        controls.add("auth")
    if list(root.glob("src/*/telemetry.py")):
        controls.add("observability")
    contract = root / ".hornero" / "contracts.json"
    operations: list[dict[str, Any]] = []
    if contract.is_file():
        try:
            operations = json.loads(contract.read_text()).get("operations", [])
        except (json.JSONDecodeError, TypeError):
            pass
    asset_set = {
        f"endpoint {item.get('path')}"
        for item in operations if isinstance(item, dict)
    }
    if "postgres" in components:
        asset_set.add("database")
    if "queue" in components:
        asset_set.add("message queue")
    assets = sorted(asset_set)
    templates = [
        ("spoofing", "auth", "Authenticate principals at every protected entry point."),
        ("tampering", "migrations", "Use reviewed schema migrations and integrity controls."),
        ("repudiation", "observability", "Record attributable security events."),
        ("information_disclosure", "auth", "Authorize access and minimize returned data."),
        ("denial_of_service", "queue", "Apply bounded queues, timeouts and rate limits."),
        ("elevation_of_privilege", "auth", "Enforce least-privilege roles."),
    ]
    threats: list[dict[str, Any]] = []
    issues: list[AssuranceIssue] = []
    for asset in assets:
        for stride, mitigation, recommendation in templates:
            threat_id = "THREAT-" + hashlib.sha256(f"{asset}\0{stride}".encode()).hexdigest()[:12]
            mitigated = mitigation in controls
            threat = {
                "threat_id": threat_id, "asset": asset, "stride": stride,
                "mitigated": mitigated, "control": mitigation if mitigated else None,
                "recommendation": recommendation,
            }
            threats.append(threat)
            if not mitigated:
                issues.append(_issue(
                    f"TM_{stride.upper()}", "threat_model", "high", "medium",
                    f"Unmitigated {stride.replace('_', ' ')} threat",
                    f"{asset} has no detected {mitigation} control.", asset,
                    recommendation, threat_id,
                ))
    result = {
        "schema": 1, "assets": assets, "trust_boundaries": ["external-to-service"],
        "threats": threats, "issues": [asdict(item) for item in issues],
    }
    if persist:
        output = layout.reports_dir(root) / "threat-model.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


_CATALOGS = {
    "soc2": {
        "CC6.1": ("Logical access controls", ["src/*/auth.py"]),
        "CC7.2": ("Security event monitoring", ["src/*/telemetry.py"]),
        "CC8.1": ("Change management", ["sdd/specs/*.md"]),
    },
    "iso27001": {
        "A.5.1": ("Information security policy", ["SECURITY.md"]),
        "A.8.8": ("Technical vulnerability management", ["sdd/reports/sbom.json"]),
        "A.8.15": ("Logging", ["src/*/telemetry.py"]),
    },
    "gdpr": {
        "ART30": ("Records of processing", [".hornero/contracts.json"]),
        "ART32": ("Security of processing", ["SECURITY.md", "src/*/auth.py"]),
        "ART35": ("Data protection impact assessment", ["sdd/reports/threat-model.json"]),
    },
    "pci": {
        "REQ6": ("Secure software lifecycle", ["sdd/reports/sbom.json"]),
        "REQ8": ("Identify and authenticate access", ["src/*/auth.py"]),
        "REQ10": ("Log and monitor access", ["src/*/telemetry.py"]),
    },
}


def compliance(
    root: Path, framework: str, *, persist: bool = True,
) -> dict[str, Any]:
    catalog = _CATALOGS.get(framework.lower())
    if catalog is None:
        raise AssuranceError(f"unknown compliance framework: {framework}")
    controls: list[dict[str, Any]] = []
    issues: list[AssuranceIssue] = []
    for control_id, (description, patterns) in sorted(catalog.items()):
        evidence = sorted({
            path.relative_to(root).as_posix()
            for pattern in patterns for path in root.glob(pattern) if path.is_file()
        })
        status = "evidenced" if evidence else "gap"
        controls.append({
            "control_id": control_id, "description": description,
            "status": status, "evidence": evidence,
        })
        if not evidence:
            issues.append(_issue(
                f"COMP_{framework.upper()}_{control_id}", "compliance", "medium", "medium",
                f"Compliance evidence gap: {control_id}", description,
                f"control:{framework}:{control_id}",
                "Provide reviewed evidence or record an explicit non-applicability decision.",
            ))
    result = {
        "schema": 1, "framework": framework.lower(), "controls": controls,
        "issues": [asdict(item) for item in issues],
        "attestation": "Evidence mapping only; not a compliance certification.",
    }
    if persist:
        output = layout.reports_dir(root) / f"compliance-{framework.lower()}.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result

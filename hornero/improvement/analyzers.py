"""Deterministic architecture, security, compliance and quality policy packs."""

from __future__ import annotations

import hashlib
import ast
import json
import re
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from hornero import layout, watermarks
from hornero.assurance import AssuranceError, compliance as assess_compliance
from hornero.assurance import supply_chain as assess_supply_chain
from hornero.assurance import threat_model as assess_threat_model
from hornero.memory import codegraph
from hornero.memory.validate import ValidationFinding, validate
from hornero.improvement.policy import apply_baseline, custom_policy_matches
from hornero.redact import redact, scan_secrets


@dataclass(frozen=True)
class FindingEvidence:
    path: str
    locator: str
    excerpt: str
    source_hash: str


@dataclass
class ImprovementFinding:
    finding_id: str
    rule_id: str
    category: str
    severity: str
    risk: str
    title: str
    description: str
    subject: str
    remediation: str
    confidence: float
    evidence: list[FindingEvidence] = field(default_factory=list)
    status: str = "open"
    first_seen: str = ""
    last_seen: str = ""
    last_result: str = ""


Analyzer = Callable[[Path], list[ImprovementFinding]]

_SHELL_TRUE = re.compile(r"\b(?:subprocess\.(?:run|Popen)|os\.system)\s*\([^\n]*shell\s*=\s*True")
_DYNAMIC_EXEC = re.compile(r"(?<![A-Za-z0-9_])(eval|exec)\s*\(")
_DERIVED_PREFIXES = ("sdd/findings/", "sdd/improvements/", ".hornero/")


def _is_derived(rel: str) -> bool:
    return rel.startswith(_DERIVED_PREFIXES)


def _is_fixture(rel: str) -> bool:
    path = Path(rel)
    return rel.startswith(("tests/", "examples/")) or "fixtures" in path.parts


def _hash(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _id(rule_id: str, subject: str) -> str:
    digest = hashlib.sha256(f"{rule_id}\0{subject}".encode()).hexdigest()[:12]
    return f"FIND-{digest}"


def _make(
    rule_id: str, category: str, severity: str, risk: str, title: str,
    description: str, subject: str, remediation: str,
    evidence: Iterable[FindingEvidence] = (), *, confidence: float = 1.0,
) -> ImprovementFinding:
    return ImprovementFinding(
        _id(rule_id, subject), rule_id, category, severity, risk, title,
        description, subject, remediation, confidence, list(evidence),
    )


def _line_evidence(root: Path, path: Path, line_number: int, line: str) -> FindingEvidence:
    return FindingEvidence(
        path.relative_to(root).as_posix(), f"L{line_number}",
        redact(line.strip())[:500], _hash(path),
    )


def security(root: Path) -> list[ImprovementFinding]:
    findings: list[ImprovementFinding] = []
    for rel in codegraph.discover_files(root):
        if _is_derived(rel) or _is_fixture(rel):
            continue
        path = root / rel
        if path.suffix.lower() not in codegraph.CODE_SUFFIXES | codegraph.CONFIG_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if secret_types := scan_secrets(text):
            findings.append(_make(
                "SEC001", "security", "critical", "high",
                "Secret-shaped value committed to project content",
                f"Detected secret shapes: {', '.join(secret_types)}", rel,
                "Remove and rotate the credential; use environment or secret storage.",
                [FindingEvidence(rel, "file", "[REDACTED]", _hash(path))],
            ))
        for line_number, line in enumerate(text.splitlines(), start=1):
            if _SHELL_TRUE.search(line):
                findings.append(_make(
                    "SEC002", "security", "high", "high",
                    "Shell execution permits command injection",
                    "A subprocess call enables shell parsing.", f"{rel}:L{line_number}",
                    "Use an argv list with shell=False and validate all path arguments.",
                    [_line_evidence(root, path, line_number, line)],
                ))
            if _DYNAMIC_EXEC.search(line):
                findings.append(_make(
                    "SEC003", "security", "high", "high",
                    "Dynamic code execution detected",
                    "eval/exec can execute untrusted project content.",
                    f"{rel}:L{line_number}",
                    "Replace dynamic execution with a structured parser or allowlisted dispatch.",
                    [_line_evidence(root, path, line_number, line)],
                ))
    return findings


def architecture(root: Path) -> list[ImprovementFinding]:
    findings: list[ImprovementFinding] = []
    for rel in codegraph.discover_files(root):
        if _is_derived(rel):
            continue
        path = root / rel
        if path.suffix not in (".py", ".js", ".ts"):
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        if len(lines) > 600:
            findings.append(_make(
                "ARCH001", "architecture", "medium", "medium",
                "Oversized module has a broad change surface",
                f"Module contains {len(lines)} lines.", rel,
                "Split cohesive responsibilities behind existing module contracts.",
                [FindingEvidence(rel, f"L1-L{len(lines)}", "", _hash(path))],
                confidence=0.85,
            ))
    return findings


def performance(root: Path) -> list[ImprovementFinding]:
    findings: list[ImprovementFinding] = []
    blocking_calls = {"time.sleep", "requests.get", "requests.post", "subprocess.run"}
    for rel in codegraph.discover_files(root):
        if _is_derived(rel) or not rel.endswith(".py"):
            continue
        path = root / rel
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, SyntaxError):
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for function in ast.walk(tree):
            if not isinstance(function, ast.AsyncFunctionDef):
                continue
            for node in ast.walk(function):
                if not isinstance(node, ast.Call):
                    continue
                name = ""
                if isinstance(node.func, ast.Attribute) and isinstance(
                    node.func.value, ast.Name
                ):
                    name = f"{node.func.value.id}.{node.func.attr}"
                if name not in blocking_calls:
                    continue
                line = lines[node.lineno - 1] if node.lineno <= len(lines) else name
                findings.append(_make(
                    "PERF001", "performance", "medium", "medium",
                    "Blocking call runs inside an async function",
                    f"{name} can block the event loop in {function.name}.",
                    f"{rel}:L{node.lineno}",
                    "Use an async-native API or move the blocking call to a worker thread.",
                    [_line_evidence(root, path, node.lineno, line)], confidence=0.9,
                ))
    return findings


def compliance(root: Path) -> list[ImprovementFinding]:
    if (root / "SECURITY.md").is_file():
        return []
    return [_make(
        "COM001", "compliance", "medium", "low",
        "Security reporting policy is missing",
        "The repository has no SECURITY.md disclosure and support policy.",
        "SECURITY.md", "Add supported-version and private disclosure instructions.",
        confidence=0.95,
    )]


def dependencies(root: Path) -> list[ImprovementFinding]:
    path = root / "pyproject.toml"
    if not path.is_file():
        return []
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return []
    deps = data.get("project", {}).get("dependencies", [])
    if not isinstance(deps, list):
        return []
    unbounded = sorted(
        str(dep) for dep in deps
        if isinstance(dep, str) and not any(op in dep for op in ("<", ">", "=", "~", "@"))
    )
    if not unbounded:
        return []
    return [_make(
        "DEP001", "dependencies", "medium", "low",
        "Runtime dependencies have no version bounds",
        f"Unbounded dependencies: {', '.join(unbounded)}", "pyproject.toml",
        "Add compatible lower/upper bounds and verify with the full test suite.",
        [FindingEvidence("pyproject.toml", "project.dependencies", ", ".join(unbounded), _hash(path))],
    )]


def quality(root: Path) -> list[ImprovementFinding]:
    findings: list[ImprovementFinding] = []
    workflows = root / ".github" / "workflows"
    if not workflows.is_dir() or not any(workflows.glob("*.yml")):
        findings.append(_make(
            "QUA001", "quality", "medium", "low",
            "Continuous integration workflow is missing",
            "No GitHub Actions YAML workflow was found.", ".github/workflows",
            "Add a deterministic workflow for tests, lint and type checking.",
        ))
    return findings


def tests(root: Path) -> list[ImprovementFinding]:
    findings: list[ImprovementFinding] = []
    test_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in sorted((root / "tests").glob("test_*.py"))
    ) if (root / "tests").is_dir() else ""
    for rel in codegraph.discover_files(root):
        if _is_derived(rel):
            continue
        path = Path(rel)
        if path.suffix != ".py" or rel.startswith("tests/") or path.name == "__init__.py":
            continue
        module_name = path.stem
        if module_name not in test_text and f"test_{module_name}.py" not in test_text:
            findings.append(_make(
                "TST001", "tests", "low", "low",
                "Source module has no visible test reference",
                f"No test imports or names module {module_name!r}.", rel,
                "Add focused behavioral tests or document why the module is indirectly covered.",
                [FindingEvidence(rel, "file", "", _hash(root / rel))],
                confidence=0.65,
            ))
    return findings


def documentation(root: Path) -> list[ImprovementFinding]:
    findings = []
    for name in ("README.md", "CHANGELOG.md"):
        if not (root / name).is_file():
            findings.append(_make(
                "DOC001", "documentation", "low", "low",
                f"{name} is missing", f"Repository has no {name}.", name,
                f"Create {name} with project-specific operational information.",
            ))
    return findings


def graph_integrity(root: Path) -> list[ImprovementFinding]:
    report = validate(root, repair=False)
    return [
        _from_validation(item) for item in report.findings
        if item.severity == "blocking"
    ]


def custom(root: Path) -> list[ImprovementFinding]:
    return [
        _make(
            item.rule_id, item.category, item.severity, item.risk,
            item.title, item.description, f"{item.path}:L{item.line}",
            item.remediation,
            [_line_evidence(root, root / item.path, item.line, item.excerpt)],
        )
        for item in custom_policy_matches(root)
    ]


def _assurance_findings(raw: list[dict[str, object]]) -> list[ImprovementFinding]:
    return [
        _make(
            str(item["rule_id"]), str(item["category"]), str(item["severity"]),
            str(item["risk"]), str(item["title"]), str(item["description"]),
            str(item["subject"]), str(item["remediation"]),
            confidence=0.9,
        )
        for item in raw
    ]


def supply_chain(root: Path) -> list[ImprovementFinding]:
    try:
        return _assurance_findings(assess_supply_chain(root, persist=False)["issues"])
    except AssuranceError:
        return []


def threat_model(root: Path) -> list[ImprovementFinding]:
    return _assurance_findings(assess_threat_model(root, persist=False)["issues"])


def compliance_catalogs(root: Path) -> list[ImprovementFinding]:
    findings: list[ImprovementFinding] = []
    for framework in ("soc2", "iso27001", "gdpr", "pci"):
        findings.extend(_assurance_findings(
            assess_compliance(root, framework, persist=False)["issues"]
        ))
    return findings


def _from_validation(item: ValidationFinding) -> ImprovementFinding:
    return _make(
        f"GRAPH_{item.code}", "graph", "high", "medium",
        "Knowledge graph validation failed", item.message, item.subject,
        "Run 'hornero validate --repair' and resolve remaining primary-record defects.",
    )


POLICY_PACKS: dict[str, Analyzer] = {
    "architecture": architecture,
    "performance": performance,
    "security": security,
    "compliance": compliance,
    "dependencies": dependencies,
    "quality": quality,
    "tests": tests,
    "documentation": documentation,
    "graph": graph_integrity,
    "custom": custom,
    "supply_chain": supply_chain,
    "threat_model": threat_model,
    "compliance_catalogs": compliance_catalogs,
}


def _load_index(root: Path) -> dict[str, ImprovementFinding]:
    path = layout.findings_dir(root) / "index.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {
            raw["finding_id"]: ImprovementFinding(
                **{
                    **raw,
                    "evidence": [FindingEvidence(**item) for item in raw.get("evidence", [])],
                }
            )
            for raw in data.get("findings", [])
        }
    except (KeyError, TypeError, json.JSONDecodeError, OSError):
        return {}


def _write_finding(root: Path, finding: ImprovementFinding) -> None:
    directory = layout.findings_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    evidence = "\n".join(
        f"- `{item.path}` {item.locator}: {item.excerpt or '(structural evidence)'} "
        f"(sha256 `{item.source_hash}`)"
        for item in finding.evidence
    ) or "- Structural repository evidence; no source excerpt."
    text = f"""---
finding: {finding.finding_id}
rule: {finding.rule_id}
category: {finding.category}
severity: {finding.severity}
risk: {finding.risk}
status: {finding.status}
subject: {json.dumps(finding.subject)}
confidence: {finding.confidence}
first_seen: {finding.first_seen}
last_seen: {finding.last_seen}
---

# {finding.finding_id} - {finding.title}

## Description

{finding.description}

## Evidence

{evidence}

## Remediation

{finding.remediation}

## Last result

{finding.last_result or "Not executed."}
"""
    (directory / f"{finding.finding_id}.md").write_text(
        redact(text), encoding="utf-8"
    )


def save(root: Path, current: list[ImprovementFinding]) -> list[ImprovementFinding]:
    previous = _load_index(root)
    head = watermarks.git_head(root) or "working-tree"
    merged: dict[str, ImprovementFinding] = {}
    for finding in current:
        old = previous.get(finding.finding_id)
        finding.first_seen = old.first_seen if old else head
        finding.last_seen = head
        if old and finding.status == "open" and old.status in (
            "planned", "ready_for_review", "applied", "dismissed"
        ):
            finding.status = old.status
            finding.last_result = old.last_result
        merged[finding.finding_id] = finding
    for finding_id, old in previous.items():
        if finding_id not in merged:
            if old.status in ("open", "planned", "ready_for_review", "applied"):
                old.status = "resolved"
            merged[finding_id] = old
    findings = sorted(merged.values(), key=lambda item: item.finding_id)
    directory = layout.findings_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "index.json").write_text(json.dumps({
        "schema": 1,
        "head_ref": head,
        "findings": [asdict(item) for item in findings],
    }, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    for finding in findings:
        _write_finding(root, finding)
    return findings


def scan(
    root: Path, *, packs: Iterable[str] | None = None, persist: bool = True,
) -> list[ImprovementFinding]:
    selected = sorted(set(packs or POLICY_PACKS))
    unknown = set(selected) - set(POLICY_PACKS)
    if unknown:
        raise ValueError(f"unknown policy packs: {sorted(unknown)}")
    findings: dict[str, ImprovementFinding] = {}
    for name in selected:
        for finding in POLICY_PACKS[name](root):
            findings[finding.finding_id] = finding
    ordered = sorted(
        findings.values(), key=lambda item: (
            {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(item.severity, 4),
            item.finding_id,
        )
    )
    apply_baseline(root, ordered)
    return save(root, ordered) if persist else ordered


def load(root: Path) -> list[ImprovementFinding]:
    return sorted(_load_index(root).values(), key=lambda item: item.finding_id)

"""Versioned, technology-neutral architecture data model."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


PROJECT_SCHEMA = "hornero.architecture.project/v1"
CONTEXT_SCHEMA = "hornero.architecture.context/v1"
RESULT_SCHEMA = "hornero.architecture.result/v1"

CORE_KINDS = frozenset({
    "system",
    "domain",
    "capability",
    "component",
    "interface",
    "dependency",
    "resource",
    "data",
    "lifecycle",
    "constraint",
    "decision",
    "quality",
    "owner",
    "deployment",
    "exception",
    "evidence",
    "profile",
    "rule",
})


class ArchitectureError(ValueError):
    """Raised when architecture material is malformed or unsafe to use."""


class Authority(StrEnum):
    """Authority classes ordered from advisory to explicit."""

    PROPOSAL = "proposal"
    INFERRED = "inferred"
    SPEC = "spec"
    RECORD = "record"
    CONTRACT = "contract"
    DECISION = "decision"


AUTHORITY_PRECEDENCE = {
    Authority.PROPOSAL: 0,
    Authority.INFERRED: 1,
    Authority.SPEC: 2,
    Authority.RECORD: 3,
    Authority.CONTRACT: 4,
    Authority.DECISION: 5,
}


@dataclass(frozen=True)
class Evidence:
    path: str
    locator: str = ""
    sha256: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class ProjectManifest:
    path: Path
    project_id: str
    archetypes: tuple[str, ...]
    languages: tuple[str, ...]
    frameworks: tuple[str, ...]
    profiles: tuple[str, ...]
    governance_mode: str
    legacy_policy: str
    raw: dict[str, Any]

    @property
    def active_profiles(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((
            "core",
            *self.archetypes,
            *self.languages,
            *self.frameworks,
            *self.profiles,
        )))


@dataclass(frozen=True)
class ArchitectureRecord:
    record_id: str
    kind: str
    title: str
    path: Path
    owner: str
    status: str
    profiles: tuple[str, ...]
    provides: tuple[str, ...]
    interfaces: tuple[str, ...]
    resources: tuple[str, ...]
    evidence: tuple[Evidence, ...]
    authority: Authority
    sha256: str
    raw: dict[str, Any]

    @property
    def graph_id(self) -> str:
        return f"architecture:{self.kind}:{self.record_id}"

    def to_dict(self, root: Path | None = None) -> dict[str, Any]:
        path = self.path
        if root is not None:
            try:
                path = path.resolve().relative_to(root.resolve())
            except ValueError:
                pass
        return {
            "id": self.record_id,
            "kind": self.kind,
            "title": self.title,
            "path": path.as_posix(),
            "owner": self.owner,
            "status": self.status,
            "profiles": list(self.profiles),
            "provides": list(self.provides),
            "interfaces": list(self.interfaces),
            "resources": list(self.resources),
            "evidence": [item.to_dict() for item in self.evidence],
            "authority": self.authority.value,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class Candidate:
    component: str
    resolution: str
    reasons: tuple[str, ...]
    evidence: tuple[Evidence, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "component": self.component,
            "resolution": self.resolution,
            "reasons": list(self.reasons),
            "evidence": [item.to_dict() for item in self.evidence],
        }


@dataclass(frozen=True)
class Resolution:
    capability: str
    resolution: str
    selected: str | None
    candidates: tuple[Candidate, ...]
    excluded: tuple[Candidate, ...]
    explanation: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability": self.capability,
            "resolution": self.resolution,
            "selected": self.selected,
            "candidates": [item.to_dict() for item in self.candidates],
            "excluded": [item.to_dict() for item in self.excluded],
            "explanation": list(self.explanation),
        }


@dataclass(frozen=True)
class ArchitectureFinding:
    code: str
    severity: str
    subject: str
    message: str
    profile: str = "core"
    rule_id: str = ""
    evidence: tuple[str, ...] = ()
    remediation: str = ""
    exception_eligible: bool = False

    @property
    def finding_id(self) -> str:
        payload = f"{self.code}\0{self.subject}\0{self.message}"
        return "ARCH-" + hashlib.sha256(payload.encode()).hexdigest()[:12]

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "code": self.code,
            "severity": self.severity,
            "subject": self.subject,
            "message": self.message,
            "profile": self.profile,
            "rule_id": self.rule_id,
            "evidence": list(self.evidence),
            "remediation": self.remediation,
            "exception_eligible": self.exception_eligible,
        }


@dataclass(frozen=True)
class ArchitectureReport:
    findings: tuple[ArchitectureFinding, ...]
    checked_specs: tuple[str, ...] = ()
    profiles: tuple[str, ...] = ()

    @property
    def blocking(self) -> int:
        return sum(item.severity == "blocking" for item in self.findings)

    @property
    def warnings(self) -> int:
        return sum(item.severity == "warning" for item in self.findings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "blocking": self.blocking,
            "warnings": self.warnings,
            "profiles": list(self.profiles),
            "checked_specs": list(self.checked_specs),
            "findings": [item.to_dict() for item in self.findings],
        }


@dataclass(frozen=True)
class ArchitectureDeclaration:
    profiles: tuple[str, ...] = ()
    domains: tuple[str, ...] = ()
    requests: tuple[str, ...] = ()
    reuses: tuple[str, ...] = ()
    extends: tuple[str, ...] = ()
    introduces: tuple[str, ...] = ()
    decisions: tuple[str, ...] = ()
    quality_budgets: dict[str, int | float | str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def canonical_hash(value: object) -> str:
    """Return a stable hash for protocol and provenance payloads."""
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return hashlib.sha256(encoded).hexdigest()

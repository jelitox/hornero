"""Semantic graph and traceability validation for decision preflights."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path

from hornero.memory import codegraph
from hornero.memory.reindex import index_staleness, reindex
from hornero.redact import scan_secrets


@dataclass(frozen=True)
class ValidationFinding:
    finding_id: str
    severity: str
    code: str
    subject: str
    message: str
    repairable: bool = False


@dataclass(frozen=True)
class ValidationReport:
    state: str
    findings: tuple[ValidationFinding, ...]
    repaired: bool = False

    @property
    def blocking(self) -> int:
        return sum(item.severity == "blocking" for item in self.findings)

    def to_dict(self) -> dict[str, object]:
        return {
            "state": self.state,
            "blocking": self.blocking,
            "repaired": self.repaired,
            "findings": [asdict(item) for item in self.findings],
        }


def _finding(
    severity: str, code: str, subject: str, message: str, *, repairable: bool = False
) -> ValidationFinding:
    digest = hashlib.sha256(f"{code}\0{subject}\0{message}".encode()).hexdigest()[:12]
    return ValidationFinding(
        f"VAL-{digest}", severity, code, subject, message, repairable
    )


def validate(root: Path, *, repair: bool = False) -> ValidationReport:
    state = index_staleness(root)
    repaired = False
    if repair and state in ("absent", "stale", "corrupt"):
        reindex(root)
        state = index_staleness(root)
        repaired = True

    findings: list[ValidationFinding] = []
    if state != "fresh":
        severity = "blocking" if state in ("corrupt", "stale") else "warning"
        findings.append(_finding(
            severity, f"INDEX_{state.upper()}", ".hornero/knowledge",
            f"knowledge index is {state}", repairable=True,
        ))
        if state in ("absent", "corrupt"):
            return ValidationReport(state, tuple(findings), repaired)

    path = codegraph.db_path(root)
    if not path.is_file():
        return ValidationReport(state, tuple(findings), repaired)
    try:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        dangling = conn.execute(
            "SELECT r.relation_id, r.src, r.dst FROM relations r "
            "LEFT JOIN entities s ON s.entity_id = r.src "
            "LEFT JOIN entities d ON d.entity_id = r.dst "
            "WHERE s.entity_id IS NULL OR d.entity_id IS NULL ORDER BY r.relation_id"
        ).fetchall()
        for row in dangling:
            findings.append(_finding(
                "blocking", "DANGLING_RELATION", row["relation_id"],
                f"semantic relation has missing endpoint: {row['src']} -> {row['dst']}",
            ))
        missing_entity_provenance = conn.execute(
            "SELECT e.entity_id FROM entities e LEFT JOIN provenance p "
            "ON p.subject_id = e.entity_id WHERE p.id IS NULL ORDER BY e.entity_id"
        ).fetchall()
        for row in missing_entity_provenance:
            findings.append(_finding(
                "blocking", "MISSING_PROVENANCE", row["entity_id"],
                "semantic entity has no provenance",
            ))
        missing_relation_provenance = conn.execute(
            "SELECT r.relation_id FROM relations r LEFT JOIN provenance p "
            "ON p.subject_id = r.relation_id WHERE p.id IS NULL "
            "ORDER BY r.relation_id"
        ).fetchall()
        for row in missing_relation_provenance:
            findings.append(_finding(
                "blocking", "MISSING_PROVENANCE", row["relation_id"],
                "semantic relation has no provenance",
            ))
        no_criteria = conn.execute(
            "SELECT e.entity_id FROM entities e WHERE e.kind='requirement' "
            "AND NOT EXISTS (SELECT 1 FROM relations r WHERE r.src=e.entity_id "
            "AND r.rel='has_criterion') ORDER BY e.entity_id"
        ).fetchall()
        for row in no_criteria:
            findings.append(_finding(
                "warning", "REQUIREMENT_WITHOUT_CRITERIA", row["entity_id"],
                "requirement has no acceptance criterion",
            ))
        no_tasks = conn.execute(
            "SELECT e.entity_id FROM entities e WHERE e.kind='requirement' "
            "AND NOT EXISTS (SELECT 1 FROM relations r WHERE r.src=e.entity_id "
            "AND r.rel='implemented_by') ORDER BY e.entity_id"
        ).fetchall()
        for row in no_tasks:
            findings.append(_finding(
                "warning", "REQUIREMENT_WITHOUT_TASK", row["entity_id"],
                "requirement has no indexed implementation task",
            ))
        for row in conn.execute(
            "SELECT concept_id, body FROM pages ORDER BY concept_id"
        ):
            if hits := scan_secrets(str(row["body"])):
                findings.append(_finding(
                    "blocking", "SECRET_IN_KNOWLEDGE", row["concept_id"],
                    f"derived page contains secret shapes: {', '.join(hits)}",
                    repairable=True,
                ))
    except sqlite3.DatabaseError as exc:
        findings.append(_finding(
            "blocking", "GRAPH_DATABASE_ERROR", str(path), str(exc),
            repairable=True,
        ))
    finally:
        if "conn" in locals():
            conn.close()
    findings.sort(key=lambda item: (item.severity, item.code, item.subject))
    return ValidationReport(state, tuple(findings), repaired)

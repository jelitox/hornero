"""Auditable finding baselines and declarative local policy rules."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from hornero import layout
from hornero.memory import codegraph

BASELINE_NAME = "baseline.json"


class PolicyError(RuntimeError):
    pass


@dataclass(frozen=True)
class PolicyMatch:
    rule_id: str
    category: str
    severity: str
    risk: str
    title: str
    description: str
    remediation: str
    path: str
    line: int
    excerpt: str


def baseline_path(root: Path) -> Path:
    return layout.findings_dir(root) / BASELINE_NAME


def load_baseline(root: Path) -> dict[str, dict[str, Any]]:
    path = baseline_path(root)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PolicyError(f"invalid finding baseline: {exc}") from exc
    if data.get("schema") != 1 or not isinstance(data.get("entries"), list):
        raise PolicyError("finding baseline must use schema 1 entries")
    result: dict[str, dict[str, Any]] = {}
    for entry in data["entries"]:
        if not isinstance(entry, dict) or not str(entry.get("finding_id", "")).startswith("FIND-"):
            raise PolicyError("baseline entry requires a FIND-* id")
        status = str(entry.get("status", ""))
        if status not in ("suppressed", "accepted_risk"):
            raise PolicyError(f"invalid baseline status: {status!r}")
        if not all(str(entry.get(key, "")).strip() for key in ("reason", "owner", "expires")):
            raise PolicyError("baseline entries require reason, owner and expires")
        try:
            date.fromisoformat(str(entry["expires"]))
        except ValueError as exc:
            raise PolicyError(f"invalid baseline expiry: {entry['expires']}") from exc
        result[str(entry["finding_id"])] = entry
    return result


def set_baseline(
    root: Path, finding_id: str, *, status: str, reason: str, owner: str,
    expires: str,
) -> Path:
    if not finding_id.startswith("FIND-"):
        raise PolicyError("baseline finding id must start with FIND-")
    if status not in ("suppressed", "accepted_risk"):
        raise PolicyError("baseline status must be suppressed or accepted_risk")
    if not reason.strip() or not owner.strip():
        raise PolicyError("baseline reason and owner are required")
    date.fromisoformat(expires)
    entries = load_baseline(root)
    entries[finding_id] = {
        "finding_id": finding_id, "status": status, "reason": reason,
        "owner": owner, "expires": expires,
    }
    path = baseline_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema": 1, "entries": [entries[key] for key in sorted(entries)],
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def baseline_status(root: Path, *, today: date | None = None) -> list[dict[str, Any]]:
    current = today or date.today()
    return [
        {**entry, "expired": date.fromisoformat(str(entry["expires"])) < current}
        for entry in load_baseline(root).values()
    ]


def apply_baseline(root: Path, findings: list[Any], *, today: date | None = None) -> None:
    entries = load_baseline(root)
    current = today or date.today()
    for finding in findings:
        entry = entries.get(finding.finding_id)
        if entry is None:
            continue
        if date.fromisoformat(str(entry["expires"])) < current:
            finding.last_result = f"baseline expired {entry['expires']}"
            continue
        finding.status = str(entry["status"])
        finding.last_result = (
            f"baseline: {entry['reason']} (owner={entry['owner']}, "
            f"expires={entry['expires']})"
        )


def custom_policy_matches(root: Path) -> list[PolicyMatch]:
    directory = root / "sdd" / "policies"
    if not directory.is_dir():
        return []
    rules: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            raise PolicyError(f"invalid policy {path}: {exc}") from exc
        if data.get("schema") != 1 or not isinstance(data.get("rules"), list):
            raise PolicyError(f"policy {path} must use schema 1 rules")
        rules.extend(data["rules"])
    output: list[PolicyMatch] = []
    for rule in rules:
        if not isinstance(rule, dict) or not isinstance(rule.get("match"), dict):
            raise PolicyError("policy rules require a match mapping")
        match = rule["match"]
        contains = str(match.get("contains", ""))
        glob = str(match.get("glob", "**/*"))
        if not contains or len(contains) > 500:
            raise PolicyError("policy match.contains must contain 1-500 characters")
        severity = str(rule.get("severity", "medium"))
        risk = str(rule.get("risk", "low"))
        if severity not in ("critical", "high", "medium", "low"):
            raise PolicyError(f"invalid policy severity: {severity}")
        if risk not in ("high", "medium", "low"):
            raise PolicyError(f"invalid policy risk: {risk}")
        for rel in codegraph.discover_files(root):
            if not PurePosixPath(rel).match(glob) or rel.startswith(("sdd/findings/", ".hornero/")):
                continue
            path = root / rel
            for number, line in enumerate(
                path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            ):
                if contains not in line:
                    continue
                output.append(PolicyMatch(
                    str(rule.get("id", "CUSTOM")),
                    str(rule.get("category", "custom")), severity, risk,
                    str(rule.get("title", rule.get("id", "Custom policy"))),
                    str(rule.get("description", "Declarative policy matched.")),
                    str(rule.get("remediation", "Resolve the local policy violation.")),
                    rel, number, line.strip(),
                ))
    return output

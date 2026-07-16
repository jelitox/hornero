"""Persistent event runtime for bounded autonomous project operations."""

from __future__ import annotations

import json
import builtins
import hashlib
import hmac
import os
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

from hornero.config import load_config
from hornero.improvement import analyzers, controller
from hornero.memory.ledger import Ledger
from hornero.redact import redact

SETTINGS_PATH = Path(".hornero/runtime.json")
_ACTIONS = {"scan", "plan", "run", "validate", "supply_chain", "threat_model", "compliance"}


class RuntimeError(builtins.RuntimeError):
    pass


@dataclass(frozen=True)
class RuntimeSettings:
    enabled: bool = False
    max_events: int = 5
    retry_limit: int = 2
    max_cost_units: int = 10
    require_sandbox: bool = True
    allow_push: bool = False
    pr_command: tuple[str, ...] = ()
    pr_env_allowlist: tuple[str, ...] = ()
    schedules: tuple[dict[str, Any], ...] = field(default_factory=tuple)


class ActionExecutor(Protocol):
    def execute(self, action: str, payload: dict[str, Any]) -> dict[str, Any]: ...


class PRProvider(Protocol):
    def create(self, branch: str, payload: dict[str, Any]) -> str: ...


def write_default(root: Path, *, enabled: bool = False) -> Path:
    path = root / SETTINGS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(json.dumps({
            "schema": 1, "enabled": enabled, "max_events": 5,
            "retry_limit": 2, "max_cost_units": 10,
            "require_sandbox": True, "allow_push": False,
            "pr_command": [], "pr_env_allowlist": [], "schedules": [],
        }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_settings(root: Path) -> RuntimeSettings:
    path = root / SETTINGS_PATH
    if not path.is_file():
        return RuntimeSettings()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"invalid runtime settings: {exc}") from exc
    allowed = {
        "schema", "enabled", "max_events", "retry_limit", "max_cost_units",
        "require_sandbox", "allow_push", "pr_command", "pr_env_allowlist",
        "schedules",
    }
    if data.get("schema") != 1 or set(data) - allowed:
        raise RuntimeError("runtime settings require schema 1 and known keys")
    for key in ("enabled", "require_sandbox", "allow_push"):
        if key in data and not isinstance(data[key], bool):
            raise RuntimeError(f"runtime {key} must be boolean")
    for key in ("max_events", "retry_limit", "max_cost_units"):
        value = data.get(key, getattr(RuntimeSettings(), key))
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise RuntimeError(f"runtime {key} must be a non-negative integer")
    for key in ("pr_command", "pr_env_allowlist"):
        if not isinstance(data.get(key, []), list) or not all(
            isinstance(item, str) and item for item in data.get(key, [])
        ):
            raise RuntimeError(f"runtime {key} must be an argv/string list")
    schedules = data.get("schedules", [])
    if not isinstance(schedules, list):
        raise RuntimeError("runtime schedules must be a list")
    for item in schedules:
        if not isinstance(item, dict) or not str(item.get("id", "")):
            raise RuntimeError("each schedule requires an id")
        if item.get("action") not in _ACTIONS:
            raise RuntimeError(f"unknown scheduled action: {item.get('action')}")
        if not isinstance(item.get("every_seconds"), (int, float)) or item["every_seconds"] <= 0:
            raise RuntimeError("schedule every_seconds must be positive")
    return RuntimeSettings(
        enabled=data.get("enabled", False), max_events=data.get("max_events", 5),
        retry_limit=data.get("retry_limit", 2),
        max_cost_units=data.get("max_cost_units", 10),
        require_sandbox=data.get("require_sandbox", True),
        allow_push=data.get("allow_push", False),
        pr_command=tuple(data.get("pr_command", [])),
        pr_env_allowlist=tuple(data.get("pr_env_allowlist", [])),
        schedules=tuple(schedules),
    )


class DefaultExecutor:
    def __init__(self, root: Path, settings: RuntimeSettings) -> None:
        self.root = root
        self.settings = settings

    def execute(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "scan":
            findings = controller.scan(self.root, packs=payload.get("packs"))
            return {"findings": len(findings)}
        if action == "plan":
            return controller.plan(self.root, limit=int(payload.get("limit", 20)))
        if action == "run":
            config = load_config(self.root)
            if self.settings.require_sandbox and (
                not config.autonomy.require_sandbox
                or not config.autonomy.sandbox_command
            ):
                raise RuntimeError(
                    "scheduled run requires autonomy.require_sandbox and sandbox_command"
                )
            results = controller.run(
                self.root, approved=set(map(str, payload.get("approved", [])))
            )
            return {"executions": [asdict(item) for item in results]}
        if action == "validate":
            from hornero.memory.validate import validate

            return validate(self.root, repair=True).to_dict()
        if action in ("supply_chain", "threat_model", "compliance"):
            from hornero.assurance import compliance, supply_chain, threat_model

            if action == "supply_chain":
                return supply_chain(self.root)
            if action == "threat_model":
                return threat_model(self.root)
            return compliance(self.root, str(payload.get("framework", "soc2")))
        raise RuntimeError(f"unsupported runtime action: {action}")


class CommandPRProvider:
    def __init__(self, root: Path, settings: RuntimeSettings) -> None:
        self.root = root
        self.settings = settings

    def create(self, branch: str, payload: dict[str, Any]) -> str:
        if not self.settings.pr_command:
            raise RuntimeError("runtime pr_command is not configured")
        env = {"PATH": os.environ.get("PATH", "")}
        for name in self.settings.pr_env_allowlist:
            if name in os.environ:
                env[name] = os.environ[name]
        request = json.dumps({"branch": branch, "payload": payload}, ensure_ascii=False)
        try:
            result = subprocess.run(
                self.settings.pr_command, cwd=self.root, input=request,
                capture_output=True, text=True, check=False, timeout=120, env=env,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError(f"PR provider failed: {exc}") from exc
        if result.returncode != 0:
            raise RuntimeError(
                f"PR provider exited {result.returncode}: {redact(result.stderr)[:500]}"
            )
        try:
            response = json.loads(result.stdout)
            url = str(response["url"])
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise RuntimeError(f"PR provider returned invalid JSON: {exc}") from exc
        if not url.startswith("https://"):
            raise RuntimeError("PR provider URL must use HTTPS")
        return url


def emit(
    root: Path, action: str, *, payload: dict[str, Any] | None = None,
    risk: str = "low", cost_units: int = 1, now: float | None = None,
) -> str:
    if action not in _ACTIONS:
        raise RuntimeError(f"unsupported runtime action: {action}")
    if risk not in ("low", "medium", "high") or cost_units <= 0:
        raise RuntimeError("event risk/cost is invalid")
    timestamp = time.time() if now is None else now
    with Ledger(root / ".hornero" / "ledger.db") as ledger:
        return ledger.emit_runtime_event(
            action, payload or {}, risk, cost_units, timestamp
        )


def ingest_webhook(
    root: Path, body: bytes, *, signature: str, key_env: str,
    now: float | None = None,
) -> tuple[str, bool]:
    if len(body) > 1024 * 1024:
        raise RuntimeError("webhook body exceeds 1 MiB")
    key = os.environ.get(key_env, "")
    if not key:
        raise RuntimeError(f"webhook requires environment variable {key_env}")
    expected = hmac.new(key.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise RuntimeError("webhook signature verification failed")
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid webhook JSON: {exc}") from exc
    if data.get("schema") != 1 or not str(data.get("delivery_id", "")):
        raise RuntimeError("webhook requires schema 1 and delivery_id")
    action = str(data.get("action", ""))
    risk = str(data.get("risk", "low"))
    cost = data.get("cost_units", 1)
    payload = data.get("payload", {})
    if action not in _ACTIONS or risk not in ("low", "medium", "high"):
        raise RuntimeError("webhook action or risk is invalid")
    if isinstance(cost, bool) or not isinstance(cost, int) or cost <= 0:
        raise RuntimeError("webhook cost_units must be positive")
    if not isinstance(payload, dict):
        raise RuntimeError("webhook payload must be an object")
    timestamp = time.time() if now is None else now
    with Ledger(root / ".hornero" / "ledger.db") as ledger:
        return ledger.emit_webhook_event(
            str(data["delivery_id"]), action, payload, risk, cost, timestamp
        )


def _materialize_schedules(
    root: Path, settings: RuntimeSettings, ledger: Ledger, now: float,
) -> list[str]:
    emitted: list[str] = []
    for schedule in settings.schedules:
        schedule_id = str(schedule["id"])
        every = float(schedule["every_seconds"])
        if not ledger.schedule_due(schedule_id, now, every):
            continue
        event_id = ledger.emit_runtime_event(
            str(schedule["action"]), dict(schedule.get("payload", {})),
            str(schedule.get("risk", "low")), int(schedule.get("cost_units", 1)), now,
        )
        ledger.mark_schedule(schedule_id, now)
        emitted.append(event_id)
    return emitted


def tick(
    root: Path, *, settings: RuntimeSettings | None = None,
    executor: ActionExecutor | None = None, pr_provider: PRProvider | None = None,
    approvals: dict[str, str] | None = None, now: float | None = None,
) -> dict[str, Any]:
    settings = settings or load_settings(root)
    if not settings.enabled:
        raise RuntimeError("runtime is disabled")
    timestamp = time.time() if now is None else now
    executor = executor or DefaultExecutor(root, settings)
    approvals = approvals or {}
    processed: list[dict[str, Any]] = []
    spent = 0
    with Ledger(root / ".hornero" / "ledger.db") as ledger:
        scheduled = _materialize_schedules(root, settings, ledger, timestamp)
        for event in ledger.runtime_events(ready_at=timestamp):
            if len(processed) >= settings.max_events:
                break
            cost = int(event["cost_units"])
            if spent + cost > settings.max_cost_units:
                break
            event_id = str(event["event_id"])
            approved_by = str(event["approved_by"] or approvals.get(event_id, ""))
            if event["risk"] in ("medium", "high") and not approved_by:
                ledger.update_runtime_event(
                    event_id, status="awaiting_approval",
                    attempts=int(event["attempts"]), next_at=timestamp,
                    result={"reason": "risk approval required"},
                )
                processed.append({"event_id": event_id, "status": "awaiting_approval"})
                continue
            attempts = int(event["attempts"]) + 1
            payload = json.loads(event["payload_json"])
            try:
                result = executor.execute(str(event["action"]), payload)
                branches = [
                    item.get("branch") for item in result.get("executions", [])
                    if isinstance(item, dict) and item.get("branch")
                ]
                pr_urls: list[str] = []
                if branches and settings.pr_command:
                    if not (
                        settings.allow_push and payload.get("allow_push") is True
                        and approved_by
                    ):
                        result["pr_status"] = "skipped: explicit push approval required"
                    else:
                        provider = pr_provider or CommandPRProvider(root, settings)
                        pr_urls = [provider.create(str(branch), payload) for branch in branches]
                result["pr_urls"] = pr_urls
                ledger.update_runtime_event(
                    event_id, status="completed", attempts=attempts,
                    next_at=timestamp, result=result, approved_by=approved_by or None,
                )
                status = "completed"
            except Exception as exc:
                status = "retry" if attempts <= settings.retry_limit else "dead"
                result = {"error": redact(str(exc))[:500]}
                ledger.update_runtime_event(
                    event_id, status=status, attempts=attempts,
                    next_at=timestamp + (2 ** attempts), result=result,
                    approved_by=approved_by or None,
                )
            spent += cost
            processed.append({"event_id": event_id, "status": status, "result": result})
        metrics = ledger.runtime_metrics()
    return {"scheduled": scheduled, "processed": processed, "spent": spent, "metrics": metrics}


def approve(root: Path, event_id: str, approved_by: str, *, now: float | None = None) -> None:
    if not approved_by.strip():
        raise RuntimeError("approval identity is required")
    timestamp = time.time() if now is None else now
    with Ledger(root / ".hornero" / "ledger.db") as ledger:
        events = {row["event_id"]: row for row in ledger.runtime_events()}
        event = events.get(event_id)
        if event is None:
            raise RuntimeError(f"unknown runtime event: {event_id}")
        ledger.update_runtime_event(
            event_id, status="queued", attempts=int(event["attempts"]),
            next_at=timestamp, result={"approval": "granted"},
            approved_by=approved_by,
        )


def feedback(
    root: Path, finding_id: str, *, helpful: bool, notes: str = "",
    now: float | None = None,
) -> float:
    finding = next(
        (item for item in analyzers.load(root) if item.finding_id == finding_id), None
    )
    if finding is None:
        raise RuntimeError(f"unknown finding: {finding_id}")
    timestamp = time.time() if now is None else now
    with Ledger(root / ".hornero" / "ledger.db") as ledger:
        ledger.record_feedback(
            finding_id, finding.rule_id, 1 if helpful else -1, notes, timestamp
        )
        return ledger.policy_weights()[finding.rule_id]


def status(root: Path) -> dict[str, Any]:
    settings = load_settings(root)
    with Ledger(root / ".hornero" / "ledger.db") as ledger:
        return {"settings": asdict(settings), "metrics": ledger.runtime_metrics(),
                "events": ledger.runtime_events()}

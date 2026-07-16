"""Bounded observe-plan-execute-verify-learn controller."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from hornero import layout, watermarks
from hornero.config import HorneroConfig, load_config
from hornero.improvement import analyzers
from hornero.improvement.analyzers import ImprovementFinding
from hornero.memory.ledger import Ledger
from hornero.memory.validate import validate
from hornero.redact import redact
from hornero.sandbox import SandboxError, SandboxLimits, SandboxRunner


class ImprovementError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExecutionResult:
    status: str
    branch: str | None
    details: str
    gates: tuple[str, ...] = ()


class ImprovementExecutor(Protocol):
    def execute(self, finding: ImprovementFinding) -> ExecutionResult: ...


_SEVERITY = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _plan_path(root: Path) -> Path:
    return layout.improvements_dir(root) / "plan.json"


def scan(root: Path, *, packs: list[str] | None = None) -> list[ImprovementFinding]:
    graph = validate(root, repair=True)
    if graph.blocking:
        raise ImprovementError(
            f"graph preflight has {graph.blocking} blocking finding(s)"
        )
    findings = analyzers.scan(root, packs=packs, persist=True)
    graph = validate(root, repair=True)
    if graph.blocking:
        raise ImprovementError(
            f"graph post-scan has {graph.blocking} blocking finding(s)"
        )
    return findings


def plan(root: Path, *, limit: int = 20) -> dict[str, object]:
    if limit <= 0:
        raise ImprovementError("plan limit must be positive")
    graph = validate(root, repair=True)
    if graph.blocking:
        raise ImprovementError(
            f"graph preflight has {graph.blocking} blocking finding(s)"
        )
    findings = analyzers.load(root)
    with Ledger(root / ".hornero" / "ledger.db") as ledger:
        weights = ledger.policy_weights()
    candidates = [item for item in findings if item.status in ("open", "planned")]
    candidates.sort(key=lambda item: (
        _SEVERITY.get(item.severity, 9),
        {"low": 0, "medium": 1, "high": 2}.get(item.risk, 9),
        -(item.confidence * weights.get(item.rule_id, 1.0)),
        item.finding_id,
    ))
    selected = candidates[:limit]
    selected_ids = {item.finding_id for item in selected}
    for finding in findings:
        if finding.finding_id in selected_ids and finding.status == "open":
            finding.status = "planned"
    analyzers.save(root, findings)
    payload: dict[str, object] = {
        "schema": 1,
        "head_ref": watermarks.git_head(root) or "working-tree",
        "items": [
            {
                "finding_id": item.finding_id,
                "severity": item.severity,
                "risk": item.risk,
                "confidence": item.confidence,
                "title": item.title,
                "remediation": item.remediation,
            }
            for item in selected
        ],
    }
    path = _plan_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    graph = validate(root, repair=True)
    if graph.blocking:
        raise ImprovementError(
            f"graph post-plan has {graph.blocking} blocking finding(s)"
        )
    return payload


class WorktreeExecutor:
    """Execute one finding in an isolated git worktree and retain only success."""

    def __init__(self, root: Path, config: HorneroConfig) -> None:
        self._root = root
        self._config = config

    def _git(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args], cwd=cwd or self._root,
            capture_output=True, text=True, check=False,
        )

    def execute(self, finding: ImprovementFinding) -> ExecutionResult:
        command = self._config.dispatch.cli_command
        if not command:
            raise ImprovementError(
                "autonomous execution requires dispatch.cli_command"
            )
        if self._config.autonomy.require_clean_worktree:
            dirty = self._git("status", "--porcelain").stdout.strip()
            if dirty:
                raise ImprovementError("working tree must be clean before autonomous run")
        branch = f"hornero/improve/{finding.finding_id.lower()}"
        if self._git("show-ref", "--verify", f"refs/heads/{branch}").returncode == 0:
            raise ImprovementError(f"improvement branch already exists: {branch}")
        worktree = Path(tempfile.mkdtemp(prefix="hornero-improve-"))
        added = False
        success = False
        gates: list[str] = []
        try:
            sandbox = SandboxRunner(
                self._config.autonomy.sandbox_command,
                require=self._config.autonomy.require_sandbox,
                limits=SandboxLimits(
                    cpu_seconds=max(1, int(self._config.dispatch.timeout_seconds)),
                    output_bytes=self._config.dispatch.max_output_bytes,
                ),
            )
        except SandboxError as exc:
            raise ImprovementError(f"sandbox unavailable: {exc}") from exc
        try:
            add = self._git("worktree", "add", "-q", "-b", branch, str(worktree), "HEAD")
            if add.returncode != 0:
                raise ImprovementError(f"git worktree add failed: {add.stderr.strip()}")
            added = True
            request = json.dumps({
                "finding": asdict(finding),
                "contract": {
                    "scope": "Implement only the evidence-backed remediation.",
                    "prohibited": [
                        "push", "merge default branch", "read or emit credentials",
                        "disable tests", "expand permissions",
                    ],
                    "result": "Return JSON with status and summary on stdout.",
                },
            }, ensure_ascii=False)
            try:
                proc = sandbox.run(
                    command, cwd=worktree, input=request,
                    timeout=self._config.dispatch.timeout_seconds,
                )
            except SandboxError as exc:
                return ExecutionResult("failed", None, f"executor failed: {exc}")
            if proc.returncode != 0:
                return ExecutionResult(
                    "failed", None,
                    f"executor exited {proc.returncode}: {redact(proc.stderr)[:500]}",
                )
            if not self._git("status", "--porcelain", cwd=worktree).stdout.strip():
                return ExecutionResult("failed", None, "executor produced no repository change")
            for gate in self._config.autonomy.gates:
                try:
                    result = sandbox.run(
                        gate, cwd=worktree,
                        timeout=self._config.dispatch.timeout_seconds,
                    )
                except SandboxError as exc:
                    return ExecutionResult(
                        "failed", None, f"gate sandbox failed: {exc}", tuple(gates)
                    )
                label = " ".join(gate)
                gates.append(f"{label}: {result.returncode}")
                if result.returncode != 0:
                    return ExecutionResult(
                        "failed", None,
                        f"gate failed: {label}: {redact(result.stderr or result.stdout)[:500]}",
                        tuple(gates),
                    )
            self._git("add", "-A", cwd=worktree)
            commit = subprocess.run(
                [
                    "git", "-c", "user.name=Hornero", "-c",
                    "user.email=hornero@invalid", "commit", "-qm",
                    f"fix: remediate {finding.finding_id}",
                ], cwd=worktree, capture_output=True, text=True,
            )
            if commit.returncode != 0:
                return ExecutionResult(
                    "failed", None, f"commit failed: {commit.stderr.strip()}",
                    tuple(gates),
                )
            success = True
            return ExecutionResult(
                "ready_for_review", branch, "changes committed; branch retained",
                tuple(gates),
            )
        finally:
            if added:
                self._git("worktree", "remove", "--force", str(worktree))
            shutil.rmtree(worktree, ignore_errors=True)
            if not success:
                self._git("branch", "-D", branch)


def run(
    root: Path, *, approved: set[str] | None = None,
    executor: ImprovementExecutor | None = None, now: float | None = None,
) -> list[ExecutionResult]:
    config = load_config(root)
    if not config.autonomy.enabled:
        raise ImprovementError("autonomy is disabled; set autonomy.enabled: true")
    graph = validate(root, repair=True)
    if graph.blocking:
        raise ImprovementError(
            f"graph preflight has {graph.blocking} blocking finding(s)"
        )
    try:
        payload = json.loads(_plan_path(root).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ImprovementError("no valid improvement plan; run 'hornero improve plan'") from exc
    by_id = {item.finding_id: item for item in analyzers.load(root)}
    approved = approved or set()
    selected: list[ImprovementFinding] = []
    for item in payload.get("items", []):
        finding_id = item.get("finding_id") if isinstance(item, dict) else None
        finding = by_id.get(str(finding_id))
        if finding is None or finding.status != "planned":
            continue
        if finding.risk not in config.autonomy.allowed_risk and finding.finding_id not in approved:
            continue
        if finding.risk in ("medium", "high") and finding.finding_id not in approved:
            continue
        selected.append(finding)
    selected = selected[:config.autonomy.max_changes]
    if not selected:
        raise ImprovementError("no planned findings are approved by the risk policy")
    executor = executor or WorktreeExecutor(root, config)
    timestamp = time.time() if now is None else now
    results: list[ExecutionResult] = []
    ledger = Ledger(root / ".hornero" / "ledger.db")
    run_id = ledger.next_run_id()
    ledger.record_run(run_id, "improve-run", timestamp)
    try:
        for finding in selected:
            try:
                result = executor.execute(finding)
            except Exception as exc:
                result = ExecutionResult("failed", None, redact(str(exc))[:500])
            finding.status = (
                "ready_for_review"
                if result.status == "ready_for_review" else "open"
            )
            finding.last_result = result.details
            ledger.record_improvement(
                run_id, finding.finding_id, result.status, result.branch,
                {"details": result.details, "gates": list(result.gates)}, timestamp,
            )
            results.append(result)
        analyzers.save(root, list(by_id.values()))
    finally:
        ledger.finish_run(run_id, timestamp)
        ledger.close()
    graph = validate(root, repair=True)
    if graph.blocking:
        raise ImprovementError(
            f"graph learning update has {graph.blocking} blocking finding(s)"
        )
    return results


def status(root: Path) -> dict[str, object]:
    findings = analyzers.load(root)
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding.status] = counts.get(finding.status, 0) + 1
    plan_items = 0
    try:
        payload = json.loads(_plan_path(root).read_text(encoding="utf-8"))
        plan_items = len(payload.get("items", []))
    except (OSError, json.JSONDecodeError):
        pass
    with Ledger(root / ".hornero" / "ledger.db") as ledger:
        runs = ledger.improvements()
    return {"findings": len(findings), "by_status": counts, "plan_items": plan_items,
            "executions": len(runs)}

"""SPEC-006 F20 sandbox, events, approvals, retries, PRs and feedback."""

import json
import sys
import hashlib
import hmac

import pytest

from hornero.cli import main
from hornero.improvement import analyzers
from hornero.runtime import (
    RuntimeSettings,
    approve,
    emit,
    feedback,
    ingest_webhook,
    status,
    tick,
)
from hornero.sandbox import SandboxError, SandboxRunner


class RecordingExecutor:
    def __init__(self, *, failures=0, branch=False):
        self.failures = failures
        self.branch = branch
        self.calls = []

    def execute(self, action, payload):
        self.calls.append((action, payload))
        if len(self.calls) <= self.failures:
            raise RuntimeError("transient fixture failure")
        if self.branch:
            return {"executions": [{
                "status": "ready_for_review", "branch": "hornero/improve/test",
                "details": "fixture", "gates": [],
            }]}
        return {"action": action, "ok": True}


class RecordingPR:
    def __init__(self):
        self.calls = []

    def create(self, branch, payload):
        self.calls.append((branch, payload))
        return "https://example.invalid/pr/1"


def _repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    return tmp_path


def test_sandbox_sanitizes_secrets_and_can_be_mandatory(tmp_path, monkeypatch):
    monkeypatch.setenv("PRIVATE_API_TOKEN", "must-not-cross-boundary")
    runner = SandboxRunner([], require=False)
    result = runner.run([
        sys.executable, "-c",
        "import os; print(os.environ.get('PRIVATE_API_TOKEN', 'absent'))",
    ], cwd=tmp_path, timeout=10)
    assert result.stdout.strip() == "absent"
    assert result.returncode == 0
    with pytest.raises(SandboxError, match="sandbox_command"):
        SandboxRunner([], require=True)


def test_runtime_budget_retry_schedule_and_metrics(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch)
    settings = RuntimeSettings(
        enabled=True, max_events=2, retry_limit=2, max_cost_units=2,
        require_sandbox=True,
        schedules=({
            "id": "daily-scan", "action": "scan", "every_seconds": 60,
            "risk": "low", "cost_units": 1,
        },),
    )
    event = emit(root, "validate", cost_units=1, now=0)
    executor = RecordingExecutor(failures=1)
    first = tick(root, settings=settings, executor=executor, now=0)
    assert first["scheduled"] and first["spent"] == 2
    statuses = {item["event_id"]: item["status"] for item in first["processed"]}
    assert statuses[event] == "retry"
    assert tick(root, settings=settings, executor=executor, now=1)["processed"] == []
    second = tick(root, settings=settings, executor=executor, now=3)
    assert second["processed"][0]["status"] == "completed"
    assert second["scheduled"] == []
    metrics = status(root)["metrics"]
    assert metrics["events"] == 2 and metrics["attempts"] >= 2


def test_risk_approval_and_explicit_push_gate_pr_provider(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch)
    settings = RuntimeSettings(
        enabled=True, allow_push=True, pr_command=("fake-pr",),
        max_events=5, max_cost_units=10,
    )
    event = emit(
        root, "run", payload={"allow_push": True}, risk="high", now=10
    )
    executor = RecordingExecutor(branch=True)
    waiting = tick(root, settings=settings, executor=executor, now=10)
    assert waiting["processed"] == [{
        "event_id": event, "status": "awaiting_approval"
    }]
    assert executor.calls == []
    approve(root, event, "owner@example.invalid", now=11)
    provider = RecordingPR()
    completed = tick(
        root, settings=settings, executor=executor, pr_provider=provider, now=11
    )
    assert completed["processed"][0]["status"] == "completed"
    assert completed["processed"][0]["result"]["pr_urls"] == [
        "https://example.invalid/pr/1"
    ]
    assert provider.calls[0][0] == "hornero/improve/test"


def test_feedback_updates_only_bounded_policy_weight(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch)
    source = root / "src" / "danger.py"
    source.parent.mkdir()
    source.write_text(
        "import subprocess\nsubprocess.run(value, shell=True)\n", encoding="utf-8"
    )
    finding = analyzers.scan(root, packs=["security"], persist=True)[0]
    low = feedback(root, finding.finding_id, helpful=False, now=1)
    assert low == 0.5
    feedback(root, finding.finding_id, helpful=True, now=2)
    high = feedback(root, finding.finding_id, helpful=True, now=3)
    assert 0.5 <= high <= 1.5
    assert status(root)["metrics"]["policy_weights"][finding.rule_id] == high


def test_runtime_cli_default_off_then_enabled_event_status(
    tmp_path, monkeypatch, capsys
):
    root = _repo(tmp_path, monkeypatch)
    assert main(["runtime", "init", "--enable"]) == 0
    assert json.loads((root / ".hornero" / "runtime.json").read_text())["enabled"]
    capsys.readouterr()
    assert main(["runtime", "emit", "validate", "--data", "{}"] ) == 0
    event_id = capsys.readouterr().out.strip()
    assert event_id.startswith("evt-")
    assert main(["runtime", "status", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["metrics"]["events"] == 1


def test_signed_webhook_has_replay_protection(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch)
    monkeypatch.setenv("TEST_WEBHOOK_KEY", "webhook-secret")
    body = json.dumps({
        "schema": 1, "delivery_id": "delivery-001", "action": "scan",
        "risk": "low", "cost_units": 1, "payload": {"packs": ["quality"]},
    }, sort_keys=True).encode()
    signature = hmac.new(b"webhook-secret", body, hashlib.sha256).hexdigest()
    first = ingest_webhook(
        root, body, signature=signature, key_env="TEST_WEBHOOK_KEY", now=1
    )
    second = ingest_webhook(
        root, body, signature=signature, key_env="TEST_WEBHOOK_KEY", now=2
    )
    assert first[1] is True and second == (first[0], False)
    with pytest.raises(RuntimeError, match="signature"):
        ingest_webhook(
            root, body, signature="0" * 64, key_env="TEST_WEBHOOK_KEY", now=3
        )

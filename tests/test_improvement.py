"""SPEC-005 F16 policy packs and bounded controller gates."""

import json
import subprocess
import sys

import pytest

from hornero.cli import main
from hornero.config import HorneroConfig
from hornero.improvement import analyzers, controller
from hornero.improvement.analyzers import ImprovementFinding
from hornero.improvement.controller import (
    ExecutionResult,
    ImprovementError,
    WorktreeExecutor,
)
from hornero.memory.ledger import Ledger
from hornero.memory import codegraph
from hornero.memory.reindex import index_staleness


class FakeExecutor:
    def __init__(self, status="ready_for_review"):
        self.status = status
        self.seen = []

    def execute(self, finding):
        self.seen.append(finding)
        return ExecutionResult(
            self.status,
            f"hornero/improve/{finding.finding_id.lower()}"
            if self.status == "ready_for_review" else None,
            "fake execution",
            ("pytest -q: 0",),
        )


def _repo(tmp_path, monkeypatch, *, dangerous=False):
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='fixture'\nversion='0.1.0'\ndependencies=['pyyaml']\n",
        encoding="utf-8",
    )
    source = tmp_path / "src" / "fixture" / "service.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "import subprocess\n\ndef run(value):\n"
        + ("    return subprocess.run(value, shell=True)\n" if dangerous else "    return value\n"),
        encoding="utf-8",
    )
    config = tmp_path / ".hornero" / "config.yaml"
    config.write_text(
        "dispatch:\n  backend_order: [mock]\n"
        "autonomy:\n  enabled: true\n  max_changes: 1\n"
        "  allowed_risk: [low]\n  gates: [[pytest, -q]]\n"
        "models: {}\n",
        encoding="utf-8",
    )
    return tmp_path


def test_policy_packs_persist_stable_evidence_backed_findings(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch, dangerous=True)
    first = controller.scan(root)
    second = controller.scan(root)
    assert [item.finding_id for item in first] == [item.finding_id for item in second]
    by_rule = {item.rule_id: item for item in first}
    assert {"SEC002", "COM001", "DEP001", "QUA001", "TST001"} <= set(by_rule)
    assert by_rule["SEC002"].risk == "high"
    assert by_rule["SEC002"].evidence[0].excerpt.endswith("shell=True)")
    index = root / "sdd" / "findings" / "index.json"
    assert index.is_file()
    assert (root / "sdd" / "findings" / f"{by_rule['SEC002'].finding_id}.md").is_file()


def test_fixed_finding_is_retained_as_resolved_history(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch, dangerous=True)
    findings = controller.scan(root)
    security = next(item for item in findings if item.rule_id == "SEC002")
    path = root / "src" / "fixture" / "service.py"
    path.write_text("def run(value):\n    return value\n", encoding="utf-8")
    controller.scan(root)
    resolved = {item.finding_id: item for item in analyzers.load(root)}
    assert resolved[security.finding_id].status == "resolved"


def test_low_risk_plan_executes_through_fake_verify_and_learn(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch)
    controller.scan(root)
    plan = controller.plan(root, limit=20)
    assert plan["items"]
    executor = FakeExecutor()
    results = controller.run(root, executor=executor, now=10.0)
    assert results == [ExecutionResult(
        "ready_for_review",
        f"hornero/improve/{executor.seen[0].finding_id.lower()}",
        "fake execution", ("pytest -q: 0",),
    )]
    finding = next(
        item for item in analyzers.load(root)
        if item.finding_id == executor.seen[0].finding_id
    )
    assert finding.status == "ready_for_review"
    assert finding.last_result == "fake execution"
    with Ledger(root / ".hornero" / "ledger.db") as ledger:
        rows = ledger.improvements(finding.finding_id)
        assert rows[0]["status"] == "ready_for_review"
    assert index_staleness(root) == "fresh"
    run_links = codegraph.semantic_related(
        root, f"finding:{finding.finding_id}", direction="out"
    )
    assert any(item["rel"] == "attempted_in" for item in run_links)


def test_high_risk_requires_explicit_finding_approval(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch, dangerous=True)
    findings = controller.scan(root)
    security = next(item for item in findings if item.rule_id == "SEC002")
    controller.plan(root, limit=1)
    with pytest.raises(ImprovementError, match="risk policy"):
        controller.run(root, executor=FakeExecutor(), now=10.0)
    executor = FakeExecutor()
    result = controller.run(
        root, approved={security.finding_id}, executor=executor, now=11.0
    )
    assert result[0].status == "ready_for_review"


def test_performance_pack_detects_blocking_call_in_async_function(
    tmp_path, monkeypatch
):
    root = _repo(tmp_path, monkeypatch)
    path = root / "src" / "fixture" / "async_service.py"
    path.write_text(
        "import time\n\nasync def poll():\n    time.sleep(1)\n",
        encoding="utf-8",
    )
    findings = analyzers.scan(root, packs=["performance"], persist=False)
    assert len(findings) == 1
    assert findings[0].rule_id == "PERF001"
    assert findings[0].evidence[0].locator == "L4"


def test_disabled_autonomy_and_cli_scan_plan_status(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, monkeypatch)
    assert main(["improve", "scan"]) == 0
    assert "improvement scan" in capsys.readouterr().out
    assert main(["improve", "plan", "--limit", "2"]) == 0
    assert "improvement plan" in capsys.readouterr().out
    assert main(["improve", "status", "--json"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["findings"] >= 1 and status["plan_items"] == 2
    config = root / ".hornero" / "config.yaml"
    config.write_text("autonomy: {enabled: false}\n", encoding="utf-8")
    with pytest.raises(ImprovementError, match="disabled"):
        controller.run(root, executor=FakeExecutor())


def test_worktree_executor_commits_only_to_isolated_branch(tmp_path):
    def git(*args):
        return subprocess.run(
            ["git", "-C", str(tmp_path), *args], capture_output=True,
            text=True, check=True,
        )

    git("init", "-q")
    (tmp_path / "README.md").write_text("baseline\n", encoding="utf-8")
    agent = tmp_path / "coding_agent.py"
    agent.write_text(
        "import json, pathlib, sys\n"
        "request = json.load(sys.stdin)\n"
        "assert request['finding']['finding_id'] == 'FIND-integration'\n"
        "pathlib.Path('AUTONOMOUS.md').write_text('isolated change\\n')\n"
        "print(json.dumps({'status': 'changed', 'summary': 'wrote file'}))\n",
        encoding="utf-8",
    )
    git("add", "-A")
    git(
        "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
        "commit", "-qm", "baseline",
    )
    config = HorneroConfig()
    config.dispatch.cli_command = [sys.executable, str(agent)]
    config.autonomy.gates = [[
        sys.executable, "-c",
        "from pathlib import Path; assert Path('AUTONOMOUS.md').read_text() "
        "== 'isolated change\\n'",
    ]]
    finding = ImprovementFinding(
        finding_id="FIND-integration", rule_id="TST999", category="tests",
        severity="low", risk="low", title="Integration fixture",
        description="Exercise the production executor.", subject="AUTONOMOUS.md",
        remediation="Create the expected file.", confidence=1.0,
    )

    result = WorktreeExecutor(tmp_path, config).execute(finding)

    assert result.status == "ready_for_review"
    assert result.branch == "hornero/improve/find-integration"
    assert not (tmp_path / "AUTONOMOUS.md").exists()
    assert git("show", f"{result.branch}:AUTONOMOUS.md").stdout == "isolated change\n"
    assert git("status", "--porcelain").stdout == ""

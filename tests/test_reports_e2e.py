"""F5 gate: generators run offline on a fixture repo; output contains every
`done` spec; zero network calls (asserted via blocked sockets)."""

import pytest

from hornero.cli import main
from hornero.memory.ledger import Ledger

DONE_SPEC = """---
spec: SPEC-001
title: CSV export
status: done
kind: new_feature
created: 2026-07-01
sources: [sig-20260701-aaaaaa]
supersedes: []
acceptance_criteria: []
---

# SPEC-001 — CSV export

Implemented in src/exporter. See ADR-001 for the format decision.
"""

APPROVED_SPEC = """---
spec: SPEC-002
title: Weekly digest
status: approved
kind: new_feature
created: 2026-07-07
sources: [sig-20260707-bbbbbb]
supersedes: []
acceptance_criteria:
  - "pytest tests/digest -q"
---

# SPEC-002 — Weekly digest

Send a digest from src/digest.
"""


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    specs = tmp_path / "sdd" / "specs"
    (specs / "SPEC-001-csv.md").write_text(DONE_SPEC, encoding="utf-8")
    (specs / "SPEC-002-digest.md").write_text(APPROVED_SPEC, encoding="utf-8")
    (tmp_path / "sdd" / "decisions" / "ADR-001-format.md").write_text(
        "# ADR-001 — CSV over XLSX for SPEC-001\n", encoding="utf-8"
    )
    (tmp_path / ".hornero" / "processed" / "note.md").write_text(
        "we want CSV", encoding="utf-8"
    )
    with Ledger(tmp_path / ".hornero" / "ledger.db") as led:
        led.record_run("r-1", "reconcile", 1.0)
        led.record_delta(
            "dlt-r-1.1-1", "r-1", "new", "CSV export", "approved", 0.9,
            {"affected_specs": [], "created_spec": "SPEC-001",
             "evidence": [{"signal_id": "sig-20260701-aaaaaa",
                           "excerpt": "x", "locator": "L1"}]},
        )
        led.record_dispatch(
            "SPEC-001", "r-2", "completed",
            "https://example.invalid/pr/SPEC-001-1", "hornero/SPEC-001",
            "/log", 2.0,
        )
    assert main(["reindex"]) == 0
    return tmp_path


def test_f5_gate_all_reports_offline(repo, block_network):
    assert main(["report"]) == 0
    reports = repo / "sdd" / "reports"
    names = sorted(p.name for p in reports.glob("*.html"))
    assert names == [
        "capabilities.html", "knowledge-graph.html",
        "traceability.html", "workflows.html",
    ]
    for name in ["capabilities.html", "traceability.html", "workflows.html"]:
        assert "SPEC-001" in (reports / name).read_text(encoding="utf-8")
    assert "Hornero Knowledge Graph" in (
        reports / "knowledge-graph.html"
    ).read_text(encoding="utf-8")


def test_reports_content_specifics(repo, block_network):
    assert main(["report"]) == 0
    reports = repo / "sdd" / "reports"
    workflows = (reports / "workflows.html").read_text(encoding="utf-8")
    assert "Shipped" in workflows and "ADR-001" in workflows
    assert "<code>exporter</code>" in workflows
    trace = (reports / "traceability.html").read_text(encoding="utf-8")
    assert "sig-20260701-aaaaaa" in trace
    assert "dlt-r-1.1-1" in trace
    assert "https://example.invalid/pr/SPEC-001-1" in trace


def test_only_flag(repo, capsys):
    assert main(["report", "--only", "workflows"]) == 0
    reports = repo / "sdd" / "reports"
    assert sorted(p.name for p in reports.glob("*.html")) == [
        "knowledge-graph.html", "workflows.html",
    ]
    assert main(["report", "--only", "nonsense"]) == 1
    assert "unknown report" in capsys.readouterr().out


def test_traceability_gaps_rendered(repo, block_network):
    assert main(["report", "--only", "traceability"]) == 0
    trace = (repo / "sdd" / "reports" / "traceability.html").read_text(
        encoding="utf-8"
    )
    # SPEC-002 has no deltas/PR/merge yet: its row must show explicit gaps
    row = trace[trace.index("SPEC-002"):]
    assert '<span class="gap">—</span>' in row


def test_traceability_sdd_task_column(repo, block_network):
    # SPEC-002 §8: task ids from sdd/tasks/index/*.json show up per spec —
    # matched by feature_id (SPEC-001) or by spec-file reference (SPEC-002).
    import json

    index = repo / "sdd" / "tasks" / "index"
    (index / "csv.json").write_text(json.dumps({
        "feature_id": "SPEC-001",
        "tasks": [
            {"id": "TASK-002", "feature_id": "SPEC-001"},
            {"id": "TASK-001", "feature_id": "SPEC-001"},
        ],
    }), encoding="utf-8")
    (index / "digest.json").write_text(json.dumps({
        "tasks": [{"id": "TASK-009", "spec": "sdd/specs/SPEC-002-digest.md"}],
    }), encoding="utf-8")
    (index / "broken.json").write_text("{not json", encoding="utf-8")
    assert main(["report", "--only", "traceability"]) == 0
    trace = (repo / "sdd" / "reports" / "traceability.html").read_text(
        encoding="utf-8"
    )
    assert "<th>SDD tasks</th>" in trace
    row1 = trace[trace.index("SPEC-001"):trace.index("SPEC-002")]
    assert "TASK-001, TASK-002" in row1  # sorted, deduped
    assert "TASK-009" in trace[trace.index("SPEC-002"):]


def test_build_triggers_report_refresh(repo, block_network):
    assert main(["build", "--backend", "mock"]) == 0  # SPEC-002 is approved
    reports = repo / "sdd" / "reports"
    assert (reports / "capabilities.html").exists()
    # the refreshed report reflects the post-build state (review)
    caps = (reports / "capabilities.html").read_text(encoding="utf-8")
    assert "review" in caps


def test_deterministic_across_runs(repo, block_network):
    assert main(["report"]) == 0
    reports = repo / "sdd" / "reports"
    first = {p.name: p.read_bytes() for p in reports.glob("*.html")}
    assert main(["report"]) == 0
    second = {p.name: p.read_bytes() for p in reports.glob("*.html")}
    assert first == second

"""F9 gate: a mock dispatch produces a complete ordered trace; planted
secrets never reach trace bytes; `runs show --range` returns exact slices;
`runs adopt` registers a fixture Claude Code transcript."""

import json

import pytest

from hornero.cli import main
from hornero.flight import TraceWriter, parse_range, read_trace, slice_events
from hornero.memory.ledger import Ledger

SPEC = """---
spec: SPEC-002
title: Weekly digest
status: approved
kind: new_feature
created: 2026-07-08
sources: [sig-b]
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
    assert main(["init", "--no-wiki"]) == 0
    (tmp_path / "sdd" / "specs" / "SPEC-002-digest.md").write_text(
        SPEC, encoding="utf-8"
    )
    return tmp_path


def test_f9_gate_mock_dispatch_produces_ordered_trace(repo):
    assert main(["build", "--backend", "mock"]) == 0
    with Ledger(repo / ".hornero" / "ledger.db") as led:
        (run,) = led.agent_runs("SPEC-002")
    assert run["actor"] == "dispatch:mock" and run["status"] == "completed"
    events = read_trace(repo, run["run_ref"])
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    kinds = [e["kind"] for e in events]
    assert kinds[0] == "run.started" and kinds[-1] == "run.finished"
    assert "tool_use" in kinds and "tool_result" in kinds
    assert all(e["run_id"] == run["run_ref"] for e in events)
    # the dispatches row carries the same trace_path (spec re-specified it)
    with Ledger(repo / ".hornero" / "ledger.db") as led:
        assert led.dispatches("SPEC-002")[0]["trace_path"] == run["trace_path"]


def test_f9_gate_planted_secret_never_reaches_trace_bytes(repo, monkeypatch):
    secret = "trace-secret-value-abcdef12345"
    monkeypatch.setenv("BUILD_API_TOKEN", secret)
    # the spec body (=> brief description => trace payloads) embeds it
    spec = (repo / "sdd" / "specs" / "SPEC-002-digest.md")
    spec.write_text(spec.read_text().replace(
        "Send a digest", f"Send a digest using {secret}"), encoding="utf-8")
    assert main(["build", "--backend", "mock"]) == 0
    with Ledger(repo / ".hornero" / "ledger.db") as led:
        (run,) = led.agent_runs("SPEC-002")
    trace_dir = repo / ".hornero" / "runs" / run["run_ref"]
    for f in trace_dir.rglob("*"):
        if f.is_file():
            assert secret.encode() not in f.read_bytes()


def test_f9_gate_show_range_returns_exact_slices(repo, capsys):
    writer = TraceWriter(repo, "r-x", "test", clock=lambda: 1.0)
    writer.emit("run.started", "start")
    for i in range(5):
        writer.emit("tool_use", f"step {i}")
    writer.emit("run.finished", "end")
    with Ledger(repo / ".hornero" / "ledger.db") as led:
        led.record_agent_run("r-x", spec_id=None, task_id=None, actor="test",
                             status="completed", trace_path=str(writer.path),
                             started_at=1.0)
    assert main(["runs", "show", "r-x", "--range", "e#2:e#4"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert [li.split()[0] for li in out] == ["e#2", "e#3", "e#4"]
    assert main(["runs", "show", "r-x", "--kind", "run.finished"]) == 0
    out = capsys.readouterr().out
    assert "e#7" in out and "e#3" not in out
    assert main(["runs", "show", "r-x", "--range", "nonsense"]) == 2
    assert main(["runs", "show", "missing-run"]) == 2


def test_f9_gate_adopt_registers_transcript(repo, capsys):
    transcript = repo / "session.jsonl"
    lines = [
        {"type": "user", "message": {"content": [
            {"type": "text", "text": "fix the bug"}]}},
        {"type": "assistant", "message": {"content": [
            {"type": "thinking", "thinking": "hmm"},
            {"type": "tool_use", "name": "Edit", "input": {}}]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "content": "ok"}]}},
        {"unknown_shape": True},
    ]
    transcript.write_text(
        "\n".join(json.dumps(li) for li in lines) + "\nnot json\n",
        encoding="utf-8",
    )
    assert main(["runs", "adopt", str(transcript)]) == 0
    ref = capsys.readouterr().out.split()[2]
    assert ref.startswith("adopted-")
    events = read_trace(repo, ref)
    kinds = [e["kind"] for e in events]
    assert kinds[0] == "run.started" and kinds[-1] == "run.finished"
    assert "tool_use" in kinds and "thinking_summary" in kinds
    assert "tool_result" in kinds and "message" in kinds  # tolerant mapping
    with Ledger(repo / ".hornero" / "ledger.db") as led:
        (run,) = [r for r in led.agent_runs() if r["run_ref"] == ref]
    assert run["actor"] == "adopted:claude-code"
    assert main(["runs", "adopt", "nope.jsonl"]) == 2


def test_runs_list_and_prune(repo, capsys):
    assert main(["build", "--backend", "mock"]) == 0
    assert main(["runs", "list"]) == 0
    out = capsys.readouterr().out
    assert "dispatch:mock" in out and "1 run(s)" in out
    assert main(["runs", "list", "--spec", "SPEC-999"]) == 0
    assert "0 run(s)" in capsys.readouterr().out
    # everything is recent => nothing pruned; keep-days 0 prunes it
    assert main(["runs", "prune", "--keep-days", "30"]) == 0
    assert "pruned 0" in capsys.readouterr().out
    assert main(["runs", "prune", "--keep-days", "-1"]) == 0
    assert "pruned 1" in capsys.readouterr().out
    with Ledger(repo / ".hornero" / "ledger.db") as led:
        assert len(led.agent_runs()) == 1  # audit row survives the prune


def test_writer_rejects_unknown_kind_and_range_parses(tmp_path):
    writer = TraceWriter(tmp_path, "r", "t", clock=lambda: 0.0)
    with pytest.raises(ValueError, match="unknown trace event kind"):
        writer.emit("vibes", "nope")
    assert parse_range("e#12:e#40") == (12, 40)
    assert parse_range("e#7") == (7, 7)
    with pytest.raises(ValueError):
        parse_range("e#9:e#3")
    events = [{"seq": i, "kind": "tool_use"} for i in range(1, 6)]
    assert [e["seq"] for e in slice_events(events, None, (2, 3))] == [2, 3]

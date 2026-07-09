"""F10 gate: fixture trace -> DR with every citation mechanically verified;
unanchorable claims dropped + logged; a trivial run yields no DR."""

import json


from hornero.cli import main
from hornero.flight import TraceWriter
from hornero.memory.ledger import Ledger
from hornero.reconciler.testing import FakeLLM
from hornero.scribe import scribe_run


def _repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["init", "--no-wiki"]) == 0
    return tmp_path


def _trace(root, run_ref="r-1-spec-002", spec="SPEC-002"):
    w = TraceWriter(root, run_ref, "dispatch:mock", clock=lambda: 1.0)
    w.emit("run.started", "dispatch SPEC-002 via mock")           # e#1
    w.emit("thinking_summary", "considering approach A vs B")     # e#2
    w.emit("tool_use", "Edit src/digest.py (+12 -3)")             # e#3
    w.emit("tool_result", "edit applied")                         # e#4
    w.emit("error", "pytest failed: header order")                # e#5
    w.emit("tool_use", "Edit tests/test_digest.py (+2 -2)")       # e#6
    w.emit("run.finished", "status completed")                    # e#7
    with Ledger(root / ".hornero" / "ledger.db") as led:
        led.record_agent_run(run_ref, spec_id=spec, task_id=None,
                             actor="dispatch:mock", status="completed",
                             trace_path=str(w.path), started_at=1.0,
                             finished_at=2.0)
    return run_ref


def _response(claims_extra=None):
    sections = {
        "approach": [{"text": "Edited the digest module and its test.",
                      "cite": "e#3-e#6"}],
        "alternatives": [{"text": "Approach B was skipped as riskier.",
                          "cite": "e#2-e#3"}],
        "failures": [{"text": "First pytest run failed on header order; the "
                              "test was updated.", "cite": "e#5-e#6"}],
        "learnings": [{"text": "Header order is pinned by tests.",
                       "cite": "e#5"}],
    }
    if claims_extra:
        sections.update(claims_extra)
    return json.dumps({"title": "Weekly digest build", "sections": sections})


def test_f10_gate_dr_with_verified_citations(tmp_path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)
    ref = _trace(repo)
    llm = FakeLLM({"Trace of r-1-spec-002": _response()})
    assert scribe_run(repo, ref, llm, today="2026-07-08") == 0
    (dr,) = (repo / "sdd" / "decisions").glob("DR-001-*.md")
    text = dr.read_text(encoding="utf-8")
    assert "run_id: r-1-spec-002" in text and "spec: SPEC-002" in text
    assert "outcome: completed" in text
    assert "[e#3-e#6]" in text and "[e#5]" in text  # citations survive
    assert "## Failures and retries" in text
    # every cited range resolves against the trace (the gate's own check)
    import re

    from hornero.flight import read_trace

    seqs = {e["seq"] for e in read_trace(repo, ref)}
    for lo, hi in re.findall(r"\[e#(\d+)(?:-e#(\d+))?\]", text):
        span = range(int(lo), int(hi or lo) + 1)
        assert all(s in seqs for s in span)


def test_f10_gate_unanchored_claims_dropped_and_logged(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path, monkeypatch)
    ref = _trace(repo)
    bad = {
        "deviations": [
            {"text": "cites events that never happened", "cite": "e#40-e#50"},
            {"text": "thinking alone cannot anchor", "cite": "e#2"},
            {"text": "no citation at all", "cite": ""},
        ],
    }
    llm = FakeLLM({"Trace of r-1-spec-002": _response(bad)})
    assert scribe_run(repo, ref, llm, today="2026-07-08") == 0
    text = next((repo / "sdd" / "decisions").glob("DR-001-*.md")).read_text()
    assert "never happened" not in text
    assert "thinking alone" not in text  # S3: needs an action event
    assert "Deviations" not in text  # section emptied out entirely
    out = capsys.readouterr().out
    assert out.count("dropped unanchored claim") == 3
    with Ledger(repo / ".hornero" / "ledger.db") as led:
        drops = led.dropped_drafts()
    assert sum(d["reason"] == "unanchored_claim" for d in drops) == 3


def test_f10_gate_trivial_run_yields_no_dr(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path, monkeypatch)
    w = TraceWriter(repo, "r-trivial", "wiki:update", clock=lambda: 1.0)
    w.emit("run.started", "wiki update")
    w.emit("message", "already current")
    w.emit("run.finished", "status noop")
    exploding = FakeLLM({})  # the model must not even be consulted
    assert scribe_run(repo, "r-trivial", exploding, today="2026-07-08") == 0
    assert "no decision content" in capsys.readouterr().out
    assert list((repo / "sdd" / "decisions").glob("DR-*.md")) == []
    assert exploding.calls == []


def test_all_claims_unverifiable_yields_no_dr(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path, monkeypatch)
    ref = _trace(repo)
    llm = FakeLLM({"Trace of": json.dumps({"title": "x", "sections": {
        "approach": [{"text": "fabricated", "cite": "e#99"}]}})})
    assert scribe_run(repo, ref, llm, today="2026-07-08") == 0
    assert "no verifiable decision content" in capsys.readouterr().out
    assert list((repo / "sdd" / "decisions").glob("DR-*.md")) == []


def test_rescribe_requires_force_and_reuses_id(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path, monkeypatch)
    ref = _trace(repo)
    llm = FakeLLM({"Trace of": _response()})
    assert scribe_run(repo, ref, llm, today="2026-07-08") == 0
    assert scribe_run(repo, ref, llm, today="2026-07-08") == 0
    assert "already scribed" in capsys.readouterr().out
    assert scribe_run(repo, ref, llm, today="2026-07-09", force=True) == 0
    drs = list((repo / "sdd" / "decisions").glob("DR-*.md"))
    assert len(drs) == 1 and drs[0].name.startswith("DR-001")


def test_auto_scribe_at_dispatch_close(tmp_path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)
    (repo / "sdd" / "specs" / "SPEC-002-digest.md").write_text(
        "---\nspec: SPEC-002\ntitle: Digest\nstatus: approved\n"
        "kind: new_feature\ncreated: 2026-07-08\nsources: [sig-b]\n"
        "supersedes: []\nacceptance_criteria: []\n---\n\n# SPEC-002\n\nBody.\n",
        encoding="utf-8",
    )
    script = repo / ".hornero" / "scribe.fake.json"
    script.write_text(json.dumps({"Trace of": json.dumps({
        "title": "auto", "sections": {"approach": [
            {"text": "Mock build edited the module.", "cite": "e#2-e#4"}]}})}),
        encoding="utf-8")
    (repo / ".hornero" / "config.yaml").write_text(
        "dispatch:\n  backend_order: [mock]\n"
        "models:\n  scribe: fake:.hornero/scribe.fake.json\n",
        encoding="utf-8",
    )
    assert main(["build", "--backend", "mock"]) == 0
    assert list((repo / "sdd" / "decisions").glob("DR-001-*.md"))


def test_cli_scribe_command(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path, monkeypatch)
    ref = _trace(repo)
    assert main(["scribe", ref]) == 3  # no model configured
    script = repo / ".hornero" / "scribe.fake.json"
    script.write_text(json.dumps({"Trace of": _response()}), encoding="utf-8")
    (repo / ".hornero" / "config.yaml").write_text(
        "models:\n  scribe: fake:.hornero/scribe.fake.json\n", encoding="utf-8"
    )
    assert main(["scribe", ref]) == 0
    assert main(["scribe", "no-such-run"]) == 2

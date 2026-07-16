"""SPEC-006 F17 temporal reasoning, impact, coverage and context tests."""

import json

from hornero.cli import main
from hornero.memory import codegraph
from hornero.memory.intelligence import (
    context_pack,
    contradictions,
    coverage,
    duplicates,
    extract_proposals,
    history,
    impact,
    semantic_query,
)
from hornero.memory.reindex import reindex


def _spec(spec_id, title, body, *, supersedes=""):
    previous = f"[{supersedes}]" if supersedes else "[]"
    return f"""---
spec: {spec_id}
title: {title}
status: approved
kind: new_feature
created: 2026-07-16
sources: [sig-retention]
supersedes: {previous}
acceptance_criteria:
  - pytest tests/test_retention.py -q
---

# {title}

{body}
"""


def _repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    specs = tmp_path / "sdd" / "specs"
    (specs / "SPEC-101-retention.md").write_text(
        _spec(
            "SPEC-101", "Data retention must be enabled",
            "Data retention must be enabled for audit records.",
        ), encoding="utf-8",
    )
    (specs / "SPEC-102-no-retention.md").write_text(
        _spec(
            "SPEC-102", "Data retention must not be enabled",
            "Data retention must not be enabled for audit records.",
        ), encoding="utf-8",
    )
    (specs / "SPEC-103-retention-copy.md").write_text(
        _spec(
            "SPEC-103", "Data retention must be enabled for audits",
            "Data retention must be enabled for audit records.",
            supersedes="SPEC-101",
        ), encoding="utf-8",
    )
    source = tmp_path / "src" / "retention.py"
    source.parent.mkdir()
    source.write_text("def retain():\n    return True\n", encoding="utf-8")
    test = tmp_path / "tests" / "test_retention.py"
    test.parent.mkdir()
    test.write_text(
        "from retention import retain\n\ndef test_retain():\n    assert retain()\n",
        encoding="utf-8",
    )
    index = tmp_path / "sdd" / "tasks" / "index" / "retention.json"
    index.write_text(json.dumps({
        "feature_id": "SPEC-101",
        "tasks": [{
            "id": "TASK-901", "status": "done",
            "files": ["src/retention.py"],
        }],
    }), encoding="utf-8")
    return tmp_path


def test_temporal_snapshots_are_idempotent_and_retain_superseded_versions(
    tmp_path, monkeypatch
):
    root = _repo(tmp_path, monkeypatch)
    first = reindex(root)["graph"]["snapshot_id"]
    assert len(history(root, "requirement:SPEC-101")) == 1
    assert reindex(root)["graph"]["snapshot_id"] == first
    assert len(history(root, "requirement:SPEC-101")) == 1

    path = root / "sdd" / "specs" / "SPEC-101-retention.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "for audit records", "for regulated audit records"
        ), encoding="utf-8",
    )
    second = reindex(root)["graph"]["snapshot_id"]
    versions = history(root, "requirement:SPEC-101")
    assert second != first and len(versions) == 2
    assert [item["active"] for item in versions].count(True) == 1
    supersedes = codegraph.semantic_related(
        root, "requirement:SPEC-103", rel="supersedes", direction="out"
    )
    assert supersedes[0]["entity_id"] == "requirement:SPEC-101"


def test_reasoning_impact_coverage_query_and_context_are_bounded(
    tmp_path, monkeypatch
):
    root = _repo(tmp_path, monkeypatch)
    reindex(root)
    assert any(item.left == "requirement:SPEC-101" for item in contradictions(root))
    assert any(item.left == "requirement:SPEC-101" for item in duplicates(root))
    result = impact(root, "requirement:SPEC-101")
    assert any(item["kind"] == "task" for item in result["paths"])
    scores = {item["entity_id"]: item for item in coverage(root)}
    assert scores["requirement:SPEC-101"]["score"] == 100.0
    assert semantic_query(root, kind="requirement", text="retention")
    packed = context_pack(root, "requirement:SPEC-101", budget_tokens=30)
    assert packed["used_tokens"] <= 30 and packed["truncated"] is True


def test_ai_extraction_rejects_non_verbatim_evidence(tmp_path):
    source = tmp_path / "requirements.md"
    source.write_text("Customers require immutable audit logs.", encoding="utf-8")

    class Model:
        def complete(self, system, user):
            return json.dumps({"entities": [
                {
                    "kind": "requirement", "title": "Immutable audit logs",
                    "summary": "Keep audit logs immutable.",
                    "evidence": {
                        "excerpt": "Customers require immutable audit logs.",
                        "locator": "L1",
                    },
                },
                {
                    "kind": "risk", "title": "Fabricated",
                    "summary": "Unsupported.",
                    "evidence": {"excerpt": "Not in the source", "locator": "L9"},
                },
            ]})

    result = extract_proposals(tmp_path, source, Model(), persist=True)
    assert len(result["accepted"]) == 1 and result["rejected"] == 1
    assert result["accepted"][0]["status"] == "proposed"
    assert list((tmp_path / "sdd" / "proposals").glob("knowledge-extraction-*.json"))


def test_graph_intelligence_cli_surfaces(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, monkeypatch)
    reindex(root)
    assert main(["knowledge", "coverage", "--json"]) == 0
    assert "requirement:SPEC-101" in capsys.readouterr().out
    assert main([
        "knowledge", "impact", "requirement:SPEC-101", "--depth", "2", "--json"
    ]) == 0
    assert '"root": "requirement:SPEC-101"' in capsys.readouterr().out
    assert main(["knowledge", "history", "requirement:SPEC-101"]) == 0
    assert "active" in capsys.readouterr().out

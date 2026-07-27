"""SPEC-005 F14 semantic entities, provenance, traversal and validation."""

import json

from hornero.cli import main
from hornero.memory import codegraph
from hornero.memory.reindex import reindex
from hornero.memory.validate import validate


SPEC = """---
spec: SPEC-101
title: Account health API
status: approved
kind: new_feature
created: 2026-07-16
depends_on: [SPEC-100]
sources: [sig-health-001]
acceptance_criteria:
  - pytest tests/test_service.py -q
---

# Account health API

Expose account health.
"""

DEPENDENCY_SPEC = """---
spec: SPEC-100
title: Account platform
status: done
kind: new_feature
acceptance_criteria:
  - pytest -q
---

# Account platform

Provide the account platform.
"""


def _repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    (tmp_path / "sdd" / "specs" / "SPEC-100-platform.md").write_text(
        DEPENDENCY_SPEC, encoding="utf-8"
    )
    (tmp_path / "sdd" / "specs" / "SPEC-101-health.md").write_text(
        SPEC, encoding="utf-8"
    )
    source = tmp_path / "src" / "account" / "service.py"
    source.parent.mkdir(parents=True)
    source.write_text("def health():\n    return {'status': 'ok'}\n", encoding="utf-8")
    test = tmp_path / "tests" / "test_service.py"
    test.parent.mkdir()
    test.write_text(
        "from account.service import health\n\n\ndef test_health():\n"
        "    assert health()['status'] == 'ok'\n",
        encoding="utf-8",
    )
    index = tmp_path / "sdd" / "tasks" / "index" / "health.json"
    index.write_text(json.dumps({
        "feature_id": "SPEC-101",
        "tasks": [{
            "id": "TASK-901",
            "title": "Implement health service",
            "status": "done",
            "files": ["src/account/service.py"],
        }],
    }), encoding="utf-8")
    return tmp_path


def test_semantic_graph_connects_requirement_task_code_test_and_control(
    tmp_path, monkeypatch
):
    root = _repo(tmp_path, monkeypatch)
    manifest = reindex(root)
    assert manifest["graph"]["semantic_entities"] > 0
    assert manifest["graph"]["semantic_relations"] > 0
    report = (root / "sdd" / "reports" / "knowledge-graph.html").read_text()
    assert "semantic entities" in report
    assert "Semantic Relations" in report
    assert "requirement:SPEC-101" in report
    assert "Account health API" in report
    assert "Requirement Dependencies" in report
    requirement = codegraph.get_entity(root, "requirement:SPEC-101")
    assert requirement and requirement["kind"] == "requirement"
    assert requirement["provenance"][0]["source_path"].endswith("SPEC-101-health.md")

    req_links = codegraph.semantic_related(root, "requirement:SPEC-101")
    assert any(row["rel"] == "has_criterion" for row in req_links)
    assert any(
        row["rel"] == "depends_on"
        and row["entity_id"] == "requirement:SPEC-100"
        for row in req_links
    )
    assert any(row["entity_id"] == "task:TASK-901" for row in req_links)
    task_links = codegraph.semantic_related(root, "task:TASK-901", direction="out")
    assert any(row["entity_id"] == "file:src/account/service.py" for row in task_links)
    code_links = codegraph.semantic_related(
        root, "file:src/account/service.py", rel="verified_by", direction="out"
    )
    assert any(row["entity_id"] == "file:tests/test_service.py" for row in code_links)
    criterion = next(row["entity_id"] for row in req_links if row["rel"] == "has_criterion")
    assert any(
        row["entity_id"] == "control:quality:pytest"
        for row in codegraph.semantic_related(root, criterion, direction="out")
    )


def test_validator_is_clean_of_blocking_findings_and_cli_navigates(
    tmp_path, monkeypatch, capsys
):
    root = _repo(tmp_path, monkeypatch)
    report = validate(root, repair=True)
    assert report.state == "fresh" and report.blocking == 0
    capsys.readouterr()
    assert main(["validate", "--json"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["blocking"] == 0
    assert main(["knowledge", "entity", "requirement:SPEC-101", "--json"]) == 0
    assert "Account health API" in capsys.readouterr().out
    assert main([
        "knowledge", "relations", "requirement:SPEC-101", "--json"
    ]) == 0
    assert "implemented_by" in capsys.readouterr().out


def test_validator_detects_dangling_relation_and_missing_provenance(
    tmp_path, monkeypatch
):
    root = _repo(tmp_path, monkeypatch)
    reindex(root)
    import sqlite3

    conn = sqlite3.connect(codegraph.db_path(root))
    conn.execute(
        "INSERT INTO entities VALUES (?,?,?,?,?)",
        ("risk:orphan", "risk", "Orphan", "", "{}"),
    )
    conn.execute(
        "INSERT INTO relations VALUES (?,?,?,?,?)",
        ("relation:bad", "risk:orphan", "missing:node", "affects", "fixture"),
    )
    conn.commit()
    conn.close()
    report = validate(root)
    codes = {item.code for item in report.findings}
    assert "DANGLING_RELATION" in codes
    assert "MISSING_PROVENANCE" in codes
    assert report.blocking >= 2

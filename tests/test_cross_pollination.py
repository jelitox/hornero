"""Cross-pollination gates: structure, explorer, diff, canvas and memory."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from hornero.cli import main
from hornero.flight import TraceWriter
from hornero.memory import canvas, diffimpact, pyramid, structural
from hornero.memory.codegraph import discover_files
from hornero.memory.intelligence import context_pack
from hornero.memory.reindex import reindex


def _init(root: Path, monkeypatch) -> Path:
    monkeypatch.chdir(root)
    assert main(["init", "--no-wiki"]) == 0
    return root


def _write(root: Path, rel: str, value: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    return path


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True,
        env={
            "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "test@example.invalid",
            "PATH": "/usr/bin:/bin",
        },
    )


def test_structural_index_is_incremental_and_multilanguage(tmp_path, monkeypatch):
    root = _init(tmp_path, monkeypatch)
    _write(root, "src/app.py", "import src.lib\nclass App(Base):\n    def run(self):\n        return work()\n")
    _write(root, "src/lib.py", "def work():\n    return 1\n")
    _write(root, "web/app.ts", "import {go} from './lib'; export function start(){ go(); }\n")
    _write(root, "web/lib.ts", "export const go = () => 1;\n")
    _write(root, "web/View.svelte", "<script>import {go} from './lib'; const load = () => go();</script>\n")
    _write(root, "db/schema.sql", "CREATE TABLE users(id int); SELECT * FROM users;\n")
    payload, first = structural.build_index(root, discover_files(root))
    again, second = structural.build_index(root, discover_files(root))
    assert first.analyzed == 6 and first.reused == 0
    assert second.reused == 6 and second.analyzed == 0
    assert payload == again
    assert {item["language"] for item in payload["files"]} == {
        "python", "typescript", "svelte", "sql",
    }
    ids = {symbol["id"] for item in payload["files"] for symbol in item["symbols"]}
    assert "symbol:src/app.py#App.run" in ids
    assert "symbol:web/app.ts#start" in ids
    assert any(edge[2] == "calls" for edge in payload["edges"])


def test_reindex_builds_offline_explorer_pyramid_and_progressive_context(tmp_path, monkeypatch):
    root = _init(tmp_path, monkeypatch)
    _write(
        root, "sdd/specs/SPEC-101-health.md",
        "---\nspec: SPEC-101\ntitle: Health API\nstatus: approved\n"
        "acceptance_criteria: [pytest -q]\n---\n\nExpose health state.\n",
    )
    _write(root, "src/health.py", "def health():\n    return True\n")
    manifest = reindex(root)
    assert manifest["layers"]["structural"] is True
    assert manifest["layers"]["pyramid"] is True
    assert manifest["structural"]["symbols"] >= 1
    html = (root / "sdd/reports/knowledge-graph.html").read_text(encoding="utf-8")
    assert 'data-dashboard="offline-interactive-v1"' in html
    assert 'id="graph-search"' in html and 'id="graph-persona"' in html
    memory = pyramid.load(root)
    assert memory and memory["l2_scenarios"][0]["id"] == "scenario:SPEC-101"
    packed = context_pack(root, "requirement:SPEC-101", budget_tokens=50)
    assert packed["disclosure_order"] == ["L3", "L2", "L1", "L0"]
    assert packed["used_tokens"] <= 50
    recalled = pyramid.recall(root, "health API", max_total_chars=500)
    assert recalled["fusion"] == "rrf" and recalled["used_chars"] <= 500


def test_diff_impact_connects_changed_code_to_spec(tmp_path, monkeypatch):
    root = _init(tmp_path, monkeypatch)
    _write(
        root, "sdd/specs/SPEC-101-health.md",
        "---\nspec: SPEC-101\ntitle: Health API\nstatus: approved\n"
        "acceptance_criteria: [pytest -q]\n---\n\nExpose health state.\n",
    )
    _write(root, "src/health.py", "def health():\n    return True\n")
    _write(root, "sdd/tasks/index/health.json", json.dumps({
        "feature_id": "SPEC-101", "tasks": [{
            "id": "TASK-901", "status": "done", "files": ["src/health.py"],
        }],
    }))
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "baseline")
    reindex(root)
    _write(root, "src/health.py", "def health():\n    return {'ok': True}\n")
    result = diffimpact.analyze(root, write_overlay=True)
    assert "src/health.py" in result["changed"]
    assert any(item["entity_id"] == "requirement:SPEC-101" for item in result["affected"])
    assert (root / diffimpact.OVERLAY_PATH).is_file()


def test_canvas_offloads_every_event_and_supports_drilldown(tmp_path, monkeypatch):
    root = _init(tmp_path, monkeypatch)
    writer = TraceWriter(root, "run-1", "test", clock=lambda: 1.0)
    writer.emit("run.started", "start")
    writer.emit("tool_use", "pytest", {"argv": ["pytest", "-q"]})
    writer.emit("tool_result", "tests passed", {"exit_code": 0})
    writer.emit("run.finished", "done")
    run_dir = root / ".hornero/runs/run-1"
    assert (run_dir / "canvas.md").is_file()
    assert len(list((run_dir / "refs").glob("*.md"))) == 4
    assert "flowchart TD" in (run_dir / "canvas.md").read_text(encoding="utf-8")
    assert canvas.drilldown(root, "run-1", "e2")["payload"]["argv"] == ["pytest", "-q"]


def test_persona_and_skill_distillation_are_inert_proposals(tmp_path, monkeypatch):
    root = _init(tmp_path, monkeypatch)
    for index in range(1, 6):
        _write(
            root, f"sdd/decisions/DR-{index:03d}-run.md",
            f"# Run {index}\n\n## Learnings for future runs\n\n"
            "- Run deterministic tests before handoff. [e#2-e#3]\n",
        )
    persona = pyramid.propose_persona(root, trigger_every_n=5)
    assert persona["created"] is True
    assert "status: proposed" in Path(persona["path"]).read_text(encoding="utf-8")
    assert not (root / "sdd/PROJECT_PERSONA.md").exists()
    for index in range(3):
        writer = TraceWriter(root, f"skill-run-{index}", "test", clock=lambda: 1.0)
        writer.emit("run.started", "start")
        writer.emit("tool_use", "pytest test suite")
        writer.emit("tool_result", "pytest passed")
        writer.emit("tool_use", "ruff quality gate")
        writer.emit("run.finished", "done")
    proposals = pyramid.propose_skills(root, minimum_runs=3, window=3)
    assert proposals
    text = Path(proposals[0]["path"]).read_text(encoding="utf-8")
    assert "status: proposed" in text and "approval: required" in text
    assert "Trace evidence" in text

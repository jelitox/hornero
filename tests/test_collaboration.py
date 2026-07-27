from __future__ import annotations

import base64
import hashlib
import json

import pytest

from hornero.agent_services import (
    AgentServiceError,
    collect_grounded_context,
)
from hornero.collaboration import (
    create_advisory,
    create_mockup,
    promote_mockup,
    show_advisory,
    show_mockup,
    triage_advisory,
)
from hornero.config import HorneroConfig
from hornero.memory import codegraph

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNg"
    "YAAAAAMAASsJTYQAAAAASUVORK5CYII="
)

SPEC = """---
spec: SPEC-100
title: Scheduling
status: approved
kind: new_feature
created: 2026-07-26
sources: [owner]
acceptance_criteria: [pytest -q]
---

# Scheduling

Keep the existing navigation and add appointment scheduling.
"""


@pytest.fixture
def repo(tmp_path):
    (tmp_path / ".git").mkdir()
    specs = tmp_path / "sdd" / "specs"
    specs.mkdir(parents=True)
    (specs / "SPEC-100-scheduling.md").write_text(SPEC, encoding="utf-8")
    decisions = tmp_path / "sdd" / "decisions"
    decisions.mkdir()
    (decisions / "ADR-100-calendar.md").write_text(
        "# ADR-100\n\nSPEC-100 uses a weekly calendar.\n", encoding="utf-8"
    )
    (tmp_path / "README.md").write_text(
        "# Product\n\nField service scheduling for technicians.\n",
        encoding="utf-8",
    )
    return tmp_path


def _config() -> HorneroConfig:
    cfg = HorneroConfig()
    cfg.multicoders.command = ["multicoders-test"]
    return cfg


def test_grounding_uses_verbatim_approved_spec_and_decision(repo):
    context = collect_grounded_context(repo, "SPEC-100")
    assert context.requirement in context.constraints[0]["quote"]
    assert any("weekly calendar" in item["quote"] for item in context.constraints)
    for evidence in context.evidence:
        assert evidence["sha256"] == hashlib.sha256(
            evidence["content"].encode()
        ).hexdigest()


def test_advisory_is_ledgered_triaged_and_projected(repo):
    captured = {}

    def runner(command, root, subcommand, request_path, output_path, timeout, limit, **kwargs):
        request = json.loads(request_path.read_text())
        captured.update(request)
        return {
            "run_id": "runtime-1",
            "status": "completed",
            "brief_hash": "brief-hash",
            "provider_runs": [
                {
                    "provider": "codex",
                    "status": "completed",
                    "output": "finding",
                },
                {
                    "provider": "claude",
                    "status": "completed",
                    "output": "finding",
                },
            ],
            "synthesis": {
                "summary": "two perspectives",
                "findings": [
                    {
                        "finding_id": "finding-1",
                        "provider": "codex",
                        "summary": "Missing timeout",
                        "severity": "high",
                        "disposition": "ESCALATE",
                        "disposition_reason": "Awaiting explicit triage",
                    }
                ],
            },
        }

    result = create_advisory(
        repo,
        _config(),
        spec_id="SPEC-100",
        mode="review",
        question="What fails?",
        providers=["codex", "claude"],
        minimum_quorum=2,
        runner=runner,
        now=1.0,
    )
    assert result["run_id"] == "consult-000001"
    assert result["runtime_run_id"] == "runtime-1"
    assert captured["question"] == "What fails?"
    assert all(
        item["sha256"] == hashlib.sha256(item["content"].encode()).hexdigest()
        for item in captured["evidence"]
    )
    shown = show_advisory(repo, result["run_id"])
    assert shown and shown["ledger_findings"][0]["disposition"] == "ESCALATE"
    assert triage_advisory(
        repo,
        result["run_id"],
        "finding-1",
        "CONFIRM",
        "Verified against the diff",
    )
    shown = show_advisory(repo, result["run_id"])
    assert shown and shown["ledger_findings"][0]["disposition"] == "CONFIRM"
    assert codegraph.get_entity(
        repo, f"advisory_run:{result['run_id']}"
    ) is not None
    related = codegraph.semantic_related(
        repo, f"advisory_run:{result['run_id']}", direction="out"
    )
    assert any(item["rel"] == "has_perspective" for item in related)
    assert any(item["rel"] == "grounded_by" for item in related)


def test_mockup_is_manifested_projected_and_promoted(repo):
    screenshot = repo / "screen.png"
    screenshot.write_bytes(PNG)

    def runner(command, root, subcommand, request_path, output_path, timeout, limit, **kwargs):
        run_dir = kwargs["run_dir"]
        output = run_dir / "outputs" / "calendar.png"
        output.parent.mkdir(parents=True)
        output.write_bytes(PNG)
        digest = hashlib.sha256(PNG).hexdigest()
        manifest = run_dir / "manifest.json"
        result = {
            "run_id": "runtime-mockup",
            "status": "completed",
            "provider": "codex",
            "session_id": "session-1",
            "reference": {
                "sha256": digest,
                "source_path": str(screenshot),
            },
            "artifacts": [
                {
                    "view": "calendar",
                    "filename": "calendar.png",
                    "path": str(output),
                    "sha256": digest,
                    "media_type": "image/png",
                    "width": 1,
                    "height": 1,
                    "bytes": len(PNG),
                }
            ],
        }
        manifest.write_text(json.dumps(result))
        return result

    result = create_mockup(
        repo,
        _config(),
        spec_id="SPEC-100",
        request_text="Add a calendar",
        screenshot=screenshot,
        views=[{"name": "calendar", "filename": "calendar.png"}],
        runner=runner,
        now=1.0,
    )
    assert result["run_id"] == "mockup-000001"
    shown = show_mockup(repo, result["run_id"])
    assert shown and shown["ledger_artifacts"][0]["view_name"] == "calendar"
    artifact_id = shown["ledger_artifacts"][0]["artifact_id"]
    destination = repo / "docs" / "artefacts" / "calendar.png"
    promoted = promote_mockup(
        repo, result["run_id"], artifact_id, destination
    )
    assert promoted.read_bytes() == PNG
    assert codegraph.get_entity(
        repo, f"visual_artifact:{artifact_id}"
    ) is not None
    related = codegraph.semantic_related(
        repo, f"visual_artifact:{artifact_id}", direction="out"
    )
    assert any(item["rel"] == "promoted_as" for item in related)


def test_autonomous_mode_is_fail_closed(repo):
    with pytest.raises(AgentServiceError, match="disabled"):
        create_advisory(
            repo,
            _config(),
            spec_id="SPEC-100",
            mode="research",
            question="Research",
            autonomous=True,
            runner=lambda *args, **kwargs: {},
        )


def test_mockup_rejects_screenshot_outside_repository(repo, tmp_path):
    outside = tmp_path.parent / "outside-collaboration.png"
    outside.write_bytes(PNG)
    try:
        with pytest.raises(AgentServiceError, match="inside the repository"):
            create_mockup(
                repo,
                _config(),
                spec_id="SPEC-100",
                request_text="Mock it",
                screenshot=outside,
                views=[{"name": "view", "filename": "view.png"}],
                runner=lambda *args, **kwargs: {},
            )
    finally:
        outside.unlink()

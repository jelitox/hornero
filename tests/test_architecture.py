"""SPEC-013 universal architecture governance gates."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from hornero.adapters.dispatch import brief_from_spec
from hornero.agent_services import (
    build_advisory_request,
    collect_grounded_context,
)
from hornero.architecture.corpus import (
    ArchitectureCorpus,
    init_architecture,
    inventory,
)
from hornero.architecture.governance import (
    architecture_diff,
    build_context,
    check_architecture,
    preflight_spec,
)
from hornero.architecture.model import ArchitectureError
from hornero.architecture.protocol import validate_result, verify_context
from hornero.cli import main
from hornero.lifecycle import parse_spec
from hornero.memory import codegraph
from hornero.memory.reindex import reindex


def _write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _project(
    root: Path,
    *,
    profiles: list[str] | None = None,
    mode: str = "enforced",
    legacy_policy: str = "warn",
) -> Path:
    architecture = root / "sdd" / "architecture"
    for role in (
        "domains", "capabilities", "components", "interfaces", "profiles",
        "exceptions", "patterns", "quality",
    ):
        (architecture / role).mkdir(parents=True, exist_ok=True)
    _write_yaml(architecture / "project.yaml", {
        "schema": "hornero.architecture.project/v1",
        "project": {"id": "fixture", "archetypes": profiles or []},
        "stack": {"languages": [], "frameworks": []},
        "profiles": profiles or [],
        "governance": {"mode": mode, "legacy_policy": legacy_policy},
        "future_field": {"preserved": True},
    })
    return architecture


def _component(
    architecture: Path,
    component_id: str,
    *,
    provides: list[str],
    interfaces: list[str] | None = None,
    profiles: list[str] | None = None,
) -> None:
    _write_yaml(architecture / "components" / f"{component_id}.yaml", {
        "schema": "hornero.architecture.component/v1",
        "id": component_id,
        "provides": provides,
        "interfaces": interfaces or [],
        "profiles": profiles or [],
        "owner": "platform",
        "status": "active",
        "evidence": [{"path": "src/provider.py", "locator": component_id}],
    })


def _capability(
    architecture: Path,
    capability_id: str,
    providers: list[object],
    *,
    interfaces: list[str] | None = None,
) -> None:
    _write_yaml(architecture / "capabilities" / f"{capability_id}.yaml", {
        "schema": "hornero.architecture.capability/v1",
        "id": capability_id,
        "providers": providers,
        "interfaces": interfaces or [],
        "owner": "platform",
        "status": "active",
    })


def _domain(architecture: Path, domain_id: str = "scheduling") -> None:
    _write_yaml(architecture / "domains" / f"{domain_id}.yaml", {
        "schema": "hornero.architecture.domain/v1",
        "id": domain_id,
        "owner": "product",
        "status": "active",
    })


def _spec(root: Path, architecture: str, *, spec_id: str = "SPEC-101") -> Path:
    path = root / "sdd" / "specs" / f"{spec_id}-fixture.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        f"spec: {spec_id}\n"
        "title: Architecture fixture\n"
        "status: approved\n"
        "kind: new_feature\n"
        "created: 2026-07-29\n"
        "sources: [fixture]\n"
        "supersedes: []\n"
        "acceptance_criteria: [\"pytest -q\"]\n"
        f"{architecture}"
        "---\n\n# Fixture\n",
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize(
    "profile", ["monolith", "rest-service", "website", "background-worker", "library"]
)
def test_f33_init_supports_archetypes_without_overwrite(tmp_path, profile):
    written = init_architecture(tmp_path, [profile])
    assert written
    manifest = tmp_path / "sdd" / "architecture" / "project.yaml"
    original = manifest.read_text()
    assert init_architecture(tmp_path, ["website"]) == []
    assert manifest.read_text() == original
    corpus = ArchitectureCorpus(tmp_path)
    assert profile in corpus.profiles


def test_f34_resolver_covers_all_outcomes(tmp_path):
    source = tmp_path / "src" / "provider.py"
    source.parent.mkdir()
    source.write_text("class Provider: pass\n", encoding="utf-8")
    architecture = _project(tmp_path, profiles=["rest-service"])
    _component(
        architecture, "exact", provides=["exact-cap"], interfaces=["api-v1"]
    )
    _capability(architecture, "exact-cap", ["exact"], interfaces=["api-v1"])
    _component(architecture, "adapter", provides=["adapter-cap"])
    _capability(
        architecture, "adapter-cap", ["adapter"], interfaces=["required-v2"]
    )
    _component(architecture, "extension", provides=[])
    _capability(
        architecture, "extend-cap",
        [{"component": "extension", "mode": "extend"}],
    )
    _component(architecture, "choice-a", provides=["conflict-cap"])
    _component(architecture, "choice-b", provides=["conflict-cap"])
    _capability(architecture, "conflict-cap", ["choice-a", "choice-b"])

    corpus = ArchitectureCorpus(tmp_path)
    assert corpus.resolve("exact-cap").resolution == "reuse"
    assert corpus.resolve("adapter-cap").resolution == "reuse_with_adapter"
    assert corpus.resolve("extend-cap").resolution == "extend"
    assert corpus.resolve("missing-cap").resolution == "new_component"
    conflict = corpus.resolve("conflict-cap")
    assert conflict.resolution == "needs_human"
    assert [item.component for item in conflict.candidates] == [
        "choice-a", "choice-b"
    ]


def test_f34_unknown_profile_fails_closed_and_namespaced_custom_resolves(tmp_path):
    architecture = _project(tmp_path, profiles=["acme:strict"])
    corpus = ArchitectureCorpus(tmp_path)
    assert corpus.unknown_profiles == ("acme:strict",)
    _write_yaml(architecture / "profiles" / "strict.yaml", {
        "schema": "hornero.architecture.profile/v1",
        "id": "acme:strict",
        "concerns": ["ownership"],
        "rules": ["ACME-001"],
    })
    corpus = ArchitectureCorpus(tmp_path)
    assert not corpus.unknown_profiles
    assert corpus.profiles["acme:strict"].source.endswith("strict.yaml")


def test_f34_inferred_provider_cannot_be_promoted_by_resolution(tmp_path):
    source = tmp_path / "src" / "provider.py"
    source.parent.mkdir()
    source.write_text("pass\n", encoding="utf-8")
    architecture = _project(tmp_path)
    _component(architecture, "inferred", provides=["scheduling"])
    path = architecture / "components" / "inferred.yaml"
    payload = yaml.safe_load(path.read_text())
    payload["authority"] = "inferred"
    _write_yaml(path, payload)
    _capability(architecture, "scheduling", ["inferred"])
    resolution = ArchitectureCorpus(tmp_path).resolve("scheduling")
    assert resolution.resolution == "needs_human"
    assert "not approved" in resolution.excluded[0].reasons[0]


def test_f35_preflight_and_hashed_context(tmp_path):
    source = tmp_path / "src" / "provider.py"
    source.parent.mkdir()
    source.write_text("class Calendar: pass\n", encoding="utf-8")
    architecture = _project(tmp_path, profiles=["rest-service"])
    _domain(architecture)
    _component(
        architecture, "calendar", provides=["scheduling"], interfaces=["api-v1"]
    )
    _capability(architecture, "scheduling", ["calendar"], interfaces=["api-v1"])
    _spec(tmp_path, """architecture:
  profiles: [rest-service]
  domains: [scheduling]
  requests: [scheduling]
  reuses: [calendar]
  extends: []
  introduces: []
  decisions: []
  quality_budgets:
    p95_latency_ms: 250
""")
    report = preflight_spec(tmp_path, "SPEC-101")
    assert report.blocking == 0
    context = build_context(tmp_path, "SPEC-101")
    assert verify_context(context) == context
    assert context["reuse_candidates"][0]["component"] == "calendar"
    assert context["forbidden_duplications"] == ["scheduling"]

    brief = brief_from_spec(
        parse_spec(tmp_path / "sdd/specs/SPEC-101-fixture.md"),
        str(tmp_path),
        ["pytest"],
        tmp_path / "sdd" / "decisions",
    )
    assert brief["architecture_context"]["context_hash"] == context["context_hash"]
    grounded = collect_grounded_context(tmp_path, "SPEC-101")
    advisory = build_advisory_request(
        grounded,
        mode="brainstorm",
        question="How should this be implemented?",
        providers=["codex", "claude"],
        minimum_quorum=2,
        timeout_sec=60,
    )
    assert (
        advisory["architecture_context"]["context_hash"]
        == context["context_hash"]
    )


def test_f35_preflight_blocks_unjustified_duplicate_and_missing_owner(tmp_path):
    source = tmp_path / "src" / "provider.py"
    source.parent.mkdir()
    source.write_text("pass\n", encoding="utf-8")
    architecture = _project(tmp_path)
    _domain(architecture)
    _component(architecture, "shared", provides=["scheduling"])
    _capability(architecture, "scheduling", ["shared"])
    _write_yaml(architecture / "components" / "duplicate.yaml", {
        "schema": "hornero.architecture.component/v1",
        "id": "duplicate",
        "provides": [],
        "owner": "",
        "status": "active",
        "evidence": [{"path": "src/provider.py"}],
    })
    _spec(tmp_path, """architecture:
  domains: [scheduling]
  requests: [scheduling]
  reuses: []
  extends: []
  introduces: [duplicate]
  decisions: []
""")
    report = preflight_spec(tmp_path, "SPEC-101")
    codes = {item.code for item in report.findings}
    assert {"REUSE_PLAN_MISMATCH", "INTRODUCED_COMPONENT_WITHOUT_OWNER"} <= codes
    assert report.blocking >= 2


def test_f36_rules_are_profile_scoped_and_expired_exceptions_fail(tmp_path):
    source = tmp_path / "src" / "provider.py"
    source.parent.mkdir()
    source.write_text("pass\n", encoding="utf-8")
    architecture = _project(tmp_path, profiles=["website"], mode="enforced")
    _component(architecture, "web", provides=["rendering"])
    report = check_architecture(tmp_path)
    assert not any(
        item.code == "WORKER_LIFECYCLE_INCOMPLETE" for item in report.findings
    )
    _write_yaml(architecture / "exceptions" / "expired.yaml", {
        "schema": "hornero.architecture.exception/v1",
        "id": "expired",
        "title": "Expired exception",
        "owner": "platform",
        "reason": "legacy",
        "scope": "component:web",
        "approver": "architect",
        "created": "2026-01-01",
        "expires": "2026-01-02",
        "remediation": "TASK-999",
        "waives": "ARCH-OWNER-001",
        "status": "active",
    })
    report = check_architecture(tmp_path)
    assert any(item.code == "EXPIRED_EXCEPTION" for item in report.findings)
    assert report.blocking >= 1


def test_f36_exception_waiver_is_scoped_to_one_entity(tmp_path):
    source = tmp_path / "src" / "provider.py"
    source.parent.mkdir()
    source.write_text("pass\n", encoding="utf-8")
    architecture = _project(tmp_path, mode="enforced")
    for component_id in ("allowed", "still-blocked"):
        _write_yaml(architecture / "components" / f"{component_id}.yaml", {
            "schema": "hornero.architecture.component/v1",
            "id": component_id,
            "owner": "",
            "status": "active",
            "evidence": [{"path": "src/provider.py"}],
        })
    _write_yaml(architecture / "exceptions" / "scoped.yaml", {
        "schema": "hornero.architecture.exception/v1",
        "id": "scoped",
        "owner": "platform",
        "reason": "migration",
        "scope": "component:allowed",
        "approver": "architect",
        "created": "2026-07-29",
        "expires": "2099-01-01",
        "remediation": "TASK-999",
        "waives": "ARCH-OWNER-001",
        "status": "active",
    })
    findings = check_architecture(tmp_path).findings
    missing_owner_subjects = {
        item.subject for item in findings if item.code == "MISSING_OWNER"
    }
    assert "architecture:component:allowed" not in missing_owner_subjects
    assert "architecture:component:still-blocked" in missing_owner_subjects


def test_f36_delta_distinguishes_planned_entities(tmp_path):
    architecture = _project(tmp_path)
    _component(architecture, "existing", provides=[])
    _spec(tmp_path, """architecture:
  requests: []
  reuses: [existing]
  extends: [missing-extension]
  introduces: [new-component]
  decisions: []
""")
    delta = architecture_diff(tmp_path, spec_id="SPEC-101")
    assert delta["reused"] == ["existing"]
    assert delta["extended"] == ["missing-extension"]
    assert delta["introduced"] == ["new-component"]
    assert {item["entity"] for item in delta["deviations"]} == {
        "missing-extension", "new-component"
    }


def test_f37_result_protocol_rejects_stale_or_escalated_payload(tmp_path):
    _project(tmp_path)
    _spec(tmp_path, """architecture:
  requests: []
  reuses: []
  extends: []
  introduces: []
  decisions: []
""")
    context = build_context(tmp_path, "SPEC-101")
    result = {
        "schema": "hornero.architecture.result/v1",
        "context_hash": context["context_hash"],
        "reused": [],
        "extended": [],
        "introduced": [],
        "deviations": [],
        "evidence": [],
        "unknowns": [],
    }
    assert validate_result(
        result, expected_context_hash=context["context_hash"]
    ) == result
    with pytest.raises(ArchitectureError, match="stale"):
        validate_result(result, expected_context_hash="different")
    with pytest.raises(ArchitectureError, match="unknown fields"):
        validate_result(
            {**result, "approved": True},
            expected_context_hash=context["context_hash"],
        )


def test_f37_graph_traverses_spec_capability_component_and_evidence(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    source = tmp_path / "src" / "provider.py"
    source.parent.mkdir()
    source.write_text("class Calendar: pass\n", encoding="utf-8")
    architecture = _project(tmp_path)
    _domain(architecture)
    _component(architecture, "calendar", provides=["scheduling"])
    _capability(architecture, "scheduling", ["calendar"])
    _spec(tmp_path, """architecture:
  domains: [scheduling]
  requests: [scheduling]
  reuses: [calendar]
  extends: []
  introduces: []
  decisions: []
""")
    reindex(tmp_path)
    requirement_links = codegraph.semantic_related(
        tmp_path, "requirement:SPEC-101", direction="out"
    )
    assert any(
        row["rel"] == "requests"
        and row["entity_id"] == "architecture:capability:scheduling"
        for row in requirement_links
    )
    component_links = codegraph.semantic_related(
        tmp_path, "architecture:component:calendar", direction="out"
    )
    assert any(
        row["rel"] == "provides"
        and row["entity_id"] == "architecture:capability:scheduling"
        for row in component_links
    )
    assert any(row["rel"] == "supported_by" for row in component_links)
    delta_links = codegraph.semantic_related(
        tmp_path, "architecture_delta:SPEC-101", direction="out"
    )
    assert any(
        row["rel"] == "deviates_from"
        and row["entity_id"] == "requirement:SPEC-101"
        for row in delta_links
    )


def test_build_runs_architecture_preflight_and_records_delta(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    capsys.readouterr()
    source = tmp_path / "src" / "provider.py"
    source.parent.mkdir()
    source.write_text("class Calendar: pass\n", encoding="utf-8")
    architecture = _project(tmp_path, mode="enforced")
    _domain(architecture)
    _component(architecture, "calendar", provides=["scheduling"])
    _capability(architecture, "scheduling", ["calendar"])
    spec_path = _spec(tmp_path, """architecture:
  domains: [scheduling]
  requests: [scheduling]
  reuses: [calendar]
  extends: []
  introduces: []
  decisions: []
""")
    reindex(tmp_path)
    assert main(["build", "SPEC-101", "--backend", "mock"]) == 0
    assert parse_spec(spec_path).status.value == "review"
    deltas = list((tmp_path / ".hornero" / "runs").glob(
        "*/architecture-delta.json"
    ))
    assert len(deltas) == 1
    assert json.loads(deltas[0].read_text())["deviations"] == []


def test_inventory_is_idempotent_and_never_promotes_inference(tmp_path):
    source = tmp_path / "src" / "service.py"
    source.parent.mkdir()
    source.write_text("def serve(): pass\n", encoding="utf-8")
    first = inventory(tmp_path, propose=True)
    proposal = tmp_path / str(first["proposal_path"])
    proposal.write_text(proposal.read_text() + "# manual review note\n")
    second = inventory(tmp_path, propose=True)
    assert proposal.read_text().endswith("# manual review note\n")
    assert second["authority"] == "inferred"
    assert all(
        item["authority"] == "inferred" for item in second["components"]
    )


def test_cli_check_json_and_preflight(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    capsys.readouterr()
    architecture = _project(tmp_path, mode="advisory")
    _domain(architecture)
    _spec(tmp_path, """architecture:
  domains: [scheduling]
  requests: []
  reuses: []
  extends: []
  introduces: []
  decisions: []
""")
    assert main(["architecture", "check", "--all", "--offline", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["blocking"] == 0
    assert main(["spec", "preflight", "SPEC-101", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["checked_specs"] == ["SPEC-101"]

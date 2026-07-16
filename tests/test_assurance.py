"""SPEC-006 F19 baseline, policy, supply-chain, threat and compliance gates."""

import json

from hornero.assurance import compliance, supply_chain, threat_model
from hornero.cli import main
from hornero.improvement import analyzers
from hornero.improvement.policy import baseline_status, set_baseline


def _repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    source = tmp_path / "src" / "service.py"
    source.parent.mkdir()
    source.write_text(
        "import subprocess\ndef run(value):\n    return subprocess.run(value, shell=True)\n",
        encoding="utf-8",
    )
    return tmp_path


def test_baseline_suppresses_with_owner_reason_expiry_and_fixtures_are_ignored(
    tmp_path, monkeypatch
):
    root = _repo(tmp_path, monkeypatch)
    fixture = root / "tests" / "test_token.py"
    fixture.parent.mkdir()
    fixture.write_text("TOKEN = 'sk-abcdefghijklmnopqrstuvwx'\n", encoding="utf-8")
    finding = analyzers.scan(root, packs=["security"], persist=False)[0]
    assert finding.rule_id == "SEC002"
    set_baseline(
        root, finding.finding_id, status="accepted_risk", reason="legacy adapter",
        owner="security@example.invalid", expires="2099-01-01",
    )
    result = analyzers.scan(root, packs=["security"], persist=False)
    assert len(result) == 1 and result[0].status == "accepted_risk"
    assert baseline_status(root)[0]["expired"] is False
    set_baseline(
        root, finding.finding_id, status="suppressed", reason="expired exception",
        owner="security@example.invalid", expires="2000-01-01",
    )
    expired = analyzers.scan(root, packs=["security"], persist=False)[0]
    assert expired.status == "open" and "expired" in expired.last_result


def test_declarative_policy_sdk_matches_bounded_literal_evidence(
    tmp_path, monkeypatch
):
    root = _repo(tmp_path, monkeypatch)
    policy = root / "sdd" / "policies" / "organization.yaml"
    policy.parent.mkdir()
    policy.write_text("""schema: 1
rules:
  - id: ORG001
    category: architecture
    severity: high
    risk: medium
    title: Direct legacy call is prohibited
    description: Use the organization adapter.
    remediation: Replace legacy_call with the supported port.
    match:
      glob: "src/*.py"
      contains: "legacy_call("
""", encoding="utf-8")
    (root / "src" / "legacy.py").write_text("legacy_call(value)\n", encoding="utf-8")
    findings = analyzers.scan(root, packs=["custom"], persist=False)
    assert len(findings) == 1 and findings[0].rule_id == "ORG001"
    assert findings[0].evidence[0].excerpt == "legacy_call(value)"


def test_supply_chain_offline_feed_threat_model_and_compliance_exports(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    assert main([
        "new", "SecurePay", "--blueprint", "production-service", "--no-git"
    ]) == 0
    root = tmp_path / "SecurePay"
    pyproject = root / "pyproject.toml"
    pyproject.write_text(
        pyproject.read_text().replace(
            "dependencies = []", 'dependencies = ["pyyaml==1.0"]'
        ), encoding="utf-8",
    )
    feed = root / "vulnerabilities.json"
    feed.write_text(json.dumps({
        "schema": 1,
        "vulnerabilities": [{
            "id": "CVE-TEST-0001", "package": "pyyaml", "versions": ["1.0"],
            "severity": "critical",
        }],
    }), encoding="utf-8")
    chain = supply_chain(root, vulnerability_feed=feed)
    assert chain["sbom"]["bomFormat"] == "CycloneDX"
    assert any(item["rule_id"] == "SC003" for item in chain["issues"])
    assert (root / "sdd" / "reports" / "sbom.json").is_file()

    model = threat_model(root)
    assert {"database", "message queue"} <= set(model["assets"])
    assert model["threats"] and all(item["mitigated"] for item in model["threats"])
    (root / "sdd" / "specs" / "SPEC-001-process.md").write_text("# Process\n")
    soc2 = compliance(root, "soc2")
    assert all(item["status"] == "evidenced" for item in soc2["controls"])
    iso = compliance(root, "iso27001")
    assert any(item["status"] == "gap" for item in iso["controls"])
    assert "not a compliance certification" in iso["attestation"]


def test_assurance_and_baseline_cli(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, monkeypatch)
    (root / "pyproject.toml").write_text(
        "[project]\nname='x'\nversion='1'\ndependencies=[]\n", encoding="utf-8"
    )
    assert main(["assurance", "supply-chain"]) == 0
    assert "issue(s)" in capsys.readouterr().out
    assert main([
        "improve", "baseline", "FIND-123456789abc", "--status", "suppressed",
        "--reason", "fixture", "--owner", "owner@example.invalid",
        "--expires", "2099-01-01",
    ]) == 0
    capsys.readouterr()
    assert main(["improve", "baseline-status", "--json"]) == 0
    assert "FIND-123456789abc" in capsys.readouterr().out

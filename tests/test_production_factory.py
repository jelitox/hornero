"""SPEC-006 F18 signed registries, upgrades, contracts and workspaces."""

import json

from hornero.blueprint_registry import sign_payload
from hornero.cli import main
from hornero.memory.reindex import reindex
from hornero.workspace import build, plan


def _payload(version, readme):
    return {
        "schema": 1,
        "components": {
            "remote-base": {
                "files": {
                    "README.md": readme,
                    "remote.txt": f"registry {version}\n",
                },
                "provides": ["project"],
            }
        },
        "blueprints": {
            "remote-service": {
                "version": version,
                "description": "Signed remote fixture",
                "components": ["remote-base"],
            }
        },
    }


def _registry(path, payload, key=b"registry-test-key"):
    path.write_text(
        json.dumps(sign_payload(payload, key), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def test_signed_registry_create_tamper_rejection_and_three_way_upgrade(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TEST_REGISTRY_KEY", "registry-test-key")
    registry = tmp_path / "registry.json"
    _registry(registry, _payload("1.0.0", "# {{project_name}} v1\n"))
    assert main([
        "new", "Remote", "--blueprint", "remote-service",
        "--registry", str(registry), "--registry-key-env", "TEST_REGISTRY_KEY",
        "--no-git",
    ]) == 0
    root = tmp_path / "Remote"
    lock = json.loads((root / ".hornero" / "blueprint.lock").read_text())
    assert lock["schema"] == 2 and lock["version"] == "1.0.0"
    assert lock["registry"]["payload_sha256"]

    _registry(registry, _payload("2.0.0", "# {{project_name}} v2\n"))
    (root / "README.md").write_text("local owner edit\n", encoding="utf-8")
    monkeypatch.chdir(root)
    assert main([
        "blueprint", "upgrade", "--registry-key-env", "TEST_REGISTRY_KEY"
    ]) == 2
    assert "diverged" in capsys.readouterr().err
    assert (root / "README.md").read_text() == "local owner edit\n"
    assert main([
        "blueprint", "upgrade", "--registry-key-env", "TEST_REGISTRY_KEY",
        "--theirs", "README.md",
    ]) == 0
    assert (root / "README.md").read_text() == "# Remote v2\n"

    envelope = json.loads(registry.read_text())
    envelope["payload"]["blueprints"]["remote-service"]["version"] = "9.0.0"
    registry.write_text(json.dumps(envelope), encoding="utf-8")
    assert main([
        "blueprint", "upgrade", "--registry-key-env", "TEST_REGISTRY_KEY"
    ]) == 2
    assert "hash mismatch" in capsys.readouterr().err


def test_production_stack_capabilities_and_contract_generation(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    assert main([
        "new", "Payments", "--blueprint", "production-service", "--no-git"
    ]) == 0
    root = tmp_path / "Payments"
    assert (root / "compose.yaml").is_file()
    assert (root / "deploy" / "main.tf").is_file()
    assert (root / "src" / "payments" / "auth.py").is_file()
    monkeypatch.chdir(root)
    assert main(["contracts", "generate"]) == 0
    openapi = json.loads(
        (root / "contracts" / "generated" / "openapi.json").read_text()
    )
    assert openapi["openapi"] == "3.1.0" and "/health" in openapi["paths"]
    assert main(["contracts", "check"]) == 0
    capsys.readouterr()
    (root / "contracts" / "generated" / "openapi.json").write_text("{}\n")
    assert main(["contracts", "check"]) == 1
    assert "changed" in capsys.readouterr().out


def test_capability_resolver_and_workspace_cross_repo_plan(
    tmp_path, monkeypatch, capsys
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(workspace)
    assert main(["blueprint", "resolve", "auth"]) == 0
    resolved = capsys.readouterr().out.splitlines()
    assert {"auth", "python", "base"} <= set(resolved)
    assert main(["new", "A", "--blueprint", "python-lib", "--no-git"]) == 0
    assert main(["new", "B", "--blueprint", "python-lib", "--no-git"]) == 0
    for name in ("A", "B"):
        reindex(workspace / name)
    (workspace / "A" / ".hornero" / "service-dependencies.json").write_text(
        json.dumps({"dependencies": [{"repository": "B", "service": "B"}]}),
        encoding="utf-8",
    )
    graph = build(workspace)
    assert graph["repositories"] == ["A", "B"]
    result = plan(workspace, "A/service:A")
    assert result["repositories"] == ["A", "B"]
    monkeypatch.chdir(tmp_path)
    assert main(["workspace", "graph", str(workspace), "--json"]) == 0
    assert '"repositories"' in capsys.readouterr().out

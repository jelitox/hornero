"""SPEC-005 F15 real provider adapters with simulated externals."""

import json
import subprocess
import urllib.request

import pytest

from hornero.config import HorneroConfig, ProviderConfig, load_config
from hornero.cli import main
from hornero.llm import CommandLLM, LLMError, OpenAICompatibleLLM, resolve_llm


def test_command_provider_uses_json_stdin_budget_and_redacted_audit(tmp_path):
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, '{"deltas": []}', "")

    provider = ProviderConfig(
        kind="command", command=["local-model", "--json"], max_calls=1,
    )
    llm = CommandLLM(provider, tmp_path, "local", runner=runner)
    assert llm.complete("system", "user") == '{"deltas": []}'
    payload = json.loads(calls[0][1]["input"])
    assert payload == {"system": "system", "user": "user"}
    assert calls[0][1]["cwd"] == tmp_path
    with pytest.raises(LLMError, match="budget exhausted"):
        llm.complete("system", "again")
    audit = (tmp_path / ".hornero" / "runs" / "llm-events.jsonl").read_text()
    assert "system" not in audit and "user" not in audit


def test_openai_compatible_provider_uses_env_credential_and_retries(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("TEST_LLM_TOKEN", "secret-from-env-only")
    requests: list[urllib.request.Request] = []

    def transport(request, timeout):
        requests.append(request)
        if len(requests) == 1:
            raise OSError("temporary")
        assert timeout == 3
        return json.dumps({
            "choices": [{"message": {"content": "answer"}}]
        }).encode()

    provider = ProviderConfig(
        kind="openai_compatible", base_url="https://llm.invalid/v1",
        model="test-model", api_key_env="TEST_LLM_TOKEN", timeout_seconds=3,
        retries=1,
    )
    llm = OpenAICompatibleLLM(provider, tmp_path, "remote", transport=transport)
    assert llm.complete("system", "question") == "answer"
    assert len(requests) == 2
    assert requests[-1].full_url.endswith("/v1/chat/completions")
    assert requests[-1].headers["Authorization"] == "Bearer secret-from-env-only"
    body = json.loads(requests[-1].data)
    assert body["model"] == "test-model"


def test_provider_config_and_role_resolution(tmp_path):
    config = tmp_path / ".hornero" / "config.yaml"
    config.parent.mkdir()
    config.write_text(
        "models:\n  reconciler: provider:local\n"
        "providers:\n  local:\n    kind: command\n"
        "    command: [local-model, --json]\n    max_calls: 2\n",
        encoding="utf-8",
    )
    cfg = load_config(tmp_path)
    assert cfg.providers["local"].command == ["local-model", "--json"]
    assert isinstance(resolve_llm(cfg, tmp_path, "reconciler"), CommandLLM)


def test_openai_provider_requires_env_credential(tmp_path, monkeypatch):
    monkeypatch.delenv("MISSING_LLM_TOKEN", raising=False)
    provider = ProviderConfig(
        kind="openai_compatible", base_url="https://llm.invalid/v1",
        model="m", api_key_env="MISSING_LLM_TOKEN",
    )
    llm = OpenAICompatibleLLM(provider, tmp_path, "remote")
    with pytest.raises(LLMError, match="requires environment variable"):
        llm.complete("system", "user")


def test_unknown_role_provider_fails_explicitly(tmp_path):
    cfg = HorneroConfig(models={"wiki": "provider:missing"})
    with pytest.raises(LLMError, match="unknown configured provider"):
        resolve_llm(cfg, tmp_path, "wiki")


def test_cli_reports_provider_resolution_error_without_traceback(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    (tmp_path / ".hornero" / "config.yaml").write_text(
        "models: {wiki: provider:missing}\nproviders: {}\n",
        encoding="utf-8",
    )

    assert main(["wiki", "init"]) == 1

    assert "wiki model error" in capsys.readouterr().err

"""Shared model resolution for every LLM-driven node (reconciler, wiki,
scribe). One seam — :class:`~hornero.reconciler.draft.LLMPort` — and one
config surface: ``models.<role>``. Deterministic fake scripts, local command
providers, and explicitly configured OpenAI-compatible endpoints share the
same seam.
"""

import hashlib
import json
import os
import subprocess
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from hornero.config import HorneroConfig, ProviderConfig
from hornero.redact import redact
from hornero.reconciler.draft import LLMPort
from hornero.reconciler.testing import FakeLLM


class LLMError(RuntimeError):
    pass


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]
HTTPTransport = Callable[[urllib.request.Request, float], bytes]


def _audit(root: Path, provider: str, request: str, response: str, status: str) -> None:
    path = root / ".hornero" / "runs" / "llm-events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "provider": provider,
        "request_sha256": hashlib.sha256(request.encode()).hexdigest(),
        "response_sha256": hashlib.sha256(response.encode()).hexdigest(),
        "status": status,
    }
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")


class CommandLLM:
    def __init__(
        self, config: ProviderConfig, root: Path, name: str,
        *, runner: CommandRunner = subprocess.run,
    ) -> None:
        self._config = config
        self._root = root
        self._name = name
        self._runner = runner
        self._calls = 0

    def complete(self, system: str, user: str) -> str:
        if self._calls >= self._config.max_calls:
            raise LLMError(f"provider {self._name!r} call budget exhausted")
        self._calls += 1
        request = json.dumps({"system": system, "user": user}, ensure_ascii=False)
        try:
            proc = self._runner(
                self._config.command, cwd=self._root, input=request,
                capture_output=True, text=True, check=False,
                timeout=self._config.timeout_seconds,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            _audit(self._root, self._name, request, "", "failed")
            raise LLMError(f"command provider {self._name!r} failed: {exc}") from exc
        response = proc.stdout[: self._config.max_tokens * 8]
        _audit(
            self._root, self._name, request, response,
            "completed" if proc.returncode == 0 else "failed",
        )
        if proc.returncode != 0:
            raise LLMError(
                f"command provider {self._name!r} exited {proc.returncode}: "
                f"{redact(proc.stderr)[:500]}"
            )
        return response


def _http(request: urllib.request.Request, timeout: float) -> bytes:
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


class OpenAICompatibleLLM:
    def __init__(
        self, config: ProviderConfig, root: Path, name: str,
        *, transport: HTTPTransport = _http,
    ) -> None:
        self._config = config
        self._root = root
        self._name = name
        self._transport = transport
        self._calls = 0

    def complete(self, system: str, user: str) -> str:
        if self._calls >= self._config.max_calls:
            raise LLMError(f"provider {self._name!r} call budget exhausted")
        self._calls += 1
        secret = os.environ.get(self._config.api_key_env)
        if not secret:
            raise LLMError(
                f"provider {self._name!r} requires environment variable "
                f"{self._config.api_key_env}"
            )
        payload = json.dumps({
            "model": self._config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": self._config.max_tokens,
        }, ensure_ascii=False).encode()
        endpoint = self._config.base_url.rstrip("/") + "/chat/completions"
        request = urllib.request.Request(
            endpoint, data=payload,
            headers={
                "Authorization": f"Bearer {secret}",
                "Content-Type": "application/json",
            }, method="POST",
        )
        last_error: Exception | None = None
        for _ in range(self._config.retries + 1):
            try:
                raw = self._transport(request, self._config.timeout_seconds)
                data: Any = json.loads(raw)
                response = str(data["choices"][0]["message"]["content"])
                _audit(self._root, self._name, payload.decode(), response, "completed")
                return response
            except (KeyError, IndexError, TypeError, ValueError, OSError, urllib.error.URLError) as exc:
                last_error = exc
        _audit(self._root, self._name, payload.decode(), "", "failed")
        raise LLMError(f"provider {self._name!r} failed: {last_error}")


def resolve_llm(cfg: HorneroConfig, root: Path, role: str) -> LLMPort | None:
    spec = cfg.models.get(role, "")
    if spec.startswith("fake:"):
        path = Path(spec[len("fake:"):])
        if not path.is_absolute():
            path = root / path
        return FakeLLM.from_file(path)
    if spec.startswith("provider:"):
        name = spec.removeprefix("provider:")
        provider = cfg.providers.get(name)
        if provider is None:
            raise LLMError(f"unknown configured provider {name!r} for role {role!r}")
        if provider.kind == "command":
            return CommandLLM(provider, root, name)
        return OpenAICompatibleLLM(provider, root, name)
    return None


def model_name(cfg: HorneroConfig, role: str) -> str:
    return cfg.models.get(role, "") or "(none)"

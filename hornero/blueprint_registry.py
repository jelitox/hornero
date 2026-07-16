"""Signed blueprint registry loading with bounded local/HTTPS transports."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from hornero.blueprints import Blueprint, BlueprintError, Component

MAX_REGISTRY_BYTES = 2 * 1024 * 1024
Transport = Callable[[str, float], bytes]


@dataclass(frozen=True)
class Registry:
    source: str
    payload_hash: str
    components: dict[str, Component]
    blueprints: dict[str, Blueprint]

    @property
    def identity(self) -> dict[str, str]:
        return {"source": self.source, "payload_sha256": self.payload_hash}


def _canonical(payload: object) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()


def sign_payload(payload: dict[str, Any], key: bytes) -> dict[str, Any]:
    raw = _canonical(payload)
    digest = hashlib.sha256(raw).hexdigest()
    return {
        "schema": 1, "payload": payload, "payload_sha256": digest,
        "signature": hmac.new(key, raw, hashlib.sha256).hexdigest(),
    }


def _https(source: str, timeout: float) -> bytes:
    with urllib.request.urlopen(source, timeout=timeout) as response:
        return response.read(MAX_REGISTRY_BYTES + 1)


def load_registry(
    source: str, *, key_env: str, transport: Transport = _https,
    timeout: float = 30.0,
) -> Registry:
    if source.startswith("https://"):
        raw = transport(source, timeout)
    elif "://" in source:
        raise BlueprintError("registry URL must use HTTPS")
    else:
        path = Path(source).expanduser().resolve()
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise BlueprintError(f"cannot read registry: {exc}") from exc
    if len(raw) > MAX_REGISTRY_BYTES:
        raise BlueprintError("registry exceeds 2 MiB")
    try:
        envelope = json.loads(raw)
        payload = envelope["payload"]
        expected_hash = str(envelope["payload_sha256"])
        signature = str(envelope["signature"])
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise BlueprintError(f"malformed registry envelope: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema") != 1:
        raise BlueprintError("unsupported registry payload")
    canonical = _canonical(payload)
    actual_hash = hashlib.sha256(canonical).hexdigest()
    if not hmac.compare_digest(actual_hash, expected_hash):
        raise BlueprintError("registry payload hash mismatch")
    key = os.environ.get(key_env, "")
    if not key:
        raise BlueprintError(f"registry requires environment variable {key_env}")
    expected_signature = hmac.new(
        key.encode(), canonical, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        raise BlueprintError("registry signature verification failed")

    components: dict[str, Component] = {}
    blueprints: dict[str, Blueprint] = {}
    try:
        for name, item in payload.get("components", {}).items():
            if not isinstance(item, dict) or not isinstance(item.get("files"), dict):
                raise TypeError(f"component {name!r} is malformed")
            components[str(name)] = Component(
                str(name), {str(k): str(v) for k, v in item["files"].items()},
                tuple(map(str, item.get("provides", []))),
                tuple(map(str, item.get("requires", []))),
                tuple(map(str, item.get("conflicts", []))),
            )
        for name, item in payload.get("blueprints", {}).items():
            if not isinstance(item, dict):
                raise TypeError(f"blueprint {name!r} is malformed")
            blueprints[str(name)] = Blueprint(
                str(name), str(item["version"]), str(item.get("description", "")),
                tuple(map(str, item["components"])),
            )
    except (KeyError, TypeError, ValueError) as exc:
        raise BlueprintError(f"invalid registry catalog: {exc}") from exc
    if not components or not blueprints:
        raise BlueprintError("registry must contain components and blueprints")
    return Registry(source, actual_hash, components, blueprints)


def merge_registry(
    registry: Registry,
) -> tuple[dict[str, Component], dict[str, Blueprint]]:
    from hornero.blueprints import BLUEPRINTS, COMPONENTS

    return (
        {**COMPONENTS, **registry.components},
        {**BLUEPRINTS, **registry.blueprints},
    )

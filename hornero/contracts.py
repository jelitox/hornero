"""Deterministic API, event, data and client contract generation."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from hornero.paths import contained_path

MODEL_PATH = Path(".hornero/contracts.json")
LOCK_PATH = Path(".hornero/contracts.lock")
_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")
_TYPES = {"string", "integer", "number", "boolean", "object", "array"}


class ContractError(RuntimeError):
    pass


def _load(root: Path) -> dict[str, Any]:
    try:
        model = json.loads((root / MODEL_PATH).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"invalid contract model: {exc}") from exc
    if not isinstance(model, dict) or not _NAME.fullmatch(str(model.get("service", ""))):
        raise ContractError("contract model requires a valid service name")
    for group in ("operations", "events"):
        if not isinstance(model.get(group, []), list):
            raise ContractError(f"contract model {group!r} must be a list")
    if not isinstance(model.get("models", {}), dict):
        raise ContractError("contract model 'models' must be a mapping")
    return model


def _schema(fields: dict[str, Any]) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    for name, type_name in sorted(fields.items()):
        if not _NAME.fullmatch(str(name)) or str(type_name) not in _TYPES:
            raise ContractError(f"invalid schema field {name!r}: {type_name!r}")
        properties[str(name)] = {"type": str(type_name)}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object", "properties": properties,
        "required": sorted(properties), "additionalProperties": False,
    }


def render(root: Path) -> dict[str, bytes]:
    model = _load(root)
    service = str(model["service"])
    schemas = {
        str(name): _schema(fields)
        for name, fields in sorted(model.get("models", {}).items())
        if isinstance(fields, dict)
    }
    paths: dict[str, Any] = {}
    for operation in model.get("operations", []):
        if not isinstance(operation, dict):
            raise ContractError("operation entries must be mappings")
        method = str(operation.get("method", "")).lower()
        path = str(operation.get("path", ""))
        name = str(operation.get("name", ""))
        if method not in {"get", "post", "put", "patch", "delete"}:
            raise ContractError(f"invalid operation method: {method!r}")
        if not path.startswith("/") or not _NAME.fullmatch(name):
            raise ContractError(f"invalid operation {name!r} path {path!r}")
        paths.setdefault(path, {})[method] = {
            "operationId": name,
            "responses": {"200": {"description": "Successful response"}},
        }
    openapi = {
        "openapi": "3.1.0",
        "info": {"title": service, "version": str(model.get("version", "1.0.0"))},
        "paths": paths, "components": {"schemas": schemas},
    }
    files: dict[str, bytes] = {
        "contracts/generated/openapi.json": (
            json.dumps(openapi, indent=2, sort_keys=True) + "\n"
        ).encode(),
        "contracts/generated/data-models.json": (
            json.dumps(schemas, indent=2, sort_keys=True) + "\n"
        ).encode(),
    }
    for event in model.get("events", []):
        if not isinstance(event, dict) or not _NAME.fullmatch(str(event.get("name", ""))):
            raise ContractError("event entries require a valid name")
        name = str(event["name"])
        fields = event.get("fields", {})
        if not isinstance(fields, dict):
            raise ContractError(f"event {name!r} fields must be a mapping")
        files[f"contracts/generated/events/{name}.schema.json"] = (
            json.dumps(_schema(fields), indent=2, sort_keys=True) + "\n"
        ).encode()
    operations = sorted(
        str(item["name"]) for item in model.get("operations", [])
        if isinstance(item, dict) and "name" in item
    )
    files["contracts/generated/clients/python/client.py"] = (
        '"""Generated transport-neutral client contract."""\n\n'
        + "\n".join(
            f"def {name}(transport):\n    return transport({name!r})\n"
            for name in operations
        )
    ).encode()
    return files


def generate(root: Path, *, check: bool = False) -> dict[str, object]:
    files = render(root)
    states: dict[str, str] = {}
    for rel, content in sorted(files.items()):
        path = contained_path(root, rel)
        states[rel] = "current" if path.is_file() and path.read_bytes() == content else "changed"
        if not check:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    hashes = {
        rel: hashlib.sha256(content).hexdigest() for rel, content in sorted(files.items())
    }
    if not check:
        lock = root / LOCK_PATH
        lock.write_text(
            json.dumps({"schema": 1, "files": hashes}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return {"files": states, "current": all(state == "current" for state in states.values())}

"""Versioned, composable project blueprints used by ``hornero new``."""

from __future__ import annotations

import hashlib
import base64
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from hornero.paths import contained_path, validate_relative_path

LOCK_PATH = Path(".hornero") / "blueprint.lock"
_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
_TOKEN = re.compile(r"{{([a-z][a-z0-9_]*)}}")


class BlueprintError(RuntimeError):
    pass


@dataclass(frozen=True)
class Component:
    name: str
    files: dict[str, str]
    provides: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()


@dataclass(frozen=True)
class Blueprint:
    name: str
    version: str
    description: str
    components: tuple[str, ...]


COMPONENTS = {
    "base": Component("base", {
        "README.md": "# {{project_name}}\n\n{{description}}\n",
        ".editorconfig": "root = true\n\n[*]\ncharset = utf-8\nend_of_line = lf\ninsert_final_newline = true\n",
    }, provides=("project",)),
    "python": Component("python", {
        "pyproject.toml": """[project]
name = "{{project_slug}}"
version = "0.1.0"
description = "{{description}}"
requires-python = ">=3.11"
dependencies = []

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
testpaths = ["tests"]
""",
        "src/{{package_name}}/__init__.py": "__version__ = \"0.1.0\"\n",
        "tests/test_smoke.py": "def test_smoke():\n    assert True\n",
    }, provides=("python",), requires=("project",)),
    "api": Component("api", {
        "src/{{package_name}}/api.py": """\"\"\"Dependency-free health entrypoint; replace with the selected web adapter.\"\"\"

def health() -> dict[str, str]:
    return {"status": "ok", "service": "{{project_slug}}"}
""",
        "tests/test_api.py": "from {{package_name}}.api import health\n\n\ndef test_health():\n    assert health()[\"status\"] == \"ok\"\n",
    }, provides=("api",), requires=("python",)),
    "web": Component("web", {
        "web/package.json": """{
  "name": "{{project_slug}}-web",
  "private": true,
  "version": "0.1.0",
  "scripts": {"test": "node --test"}
}
""",
        "web/src/index.js": "export const projectName = \"{{project_name}}\";\n",
        "web/test/index.test.js": "import test from 'node:test';\nimport assert from 'node:assert';\nimport { projectName } from '../src/index.js';\ntest('name', () => assert.ok(projectName));\n",
    }, provides=("web",), requires=("project",)),
    "docker": Component("docker", {
        "Dockerfile": "FROM python:3.11-slim\nWORKDIR /app\nCOPY . .\nCMD [\"python\", \"-m\", \"{{package_name}}.api\"]\n",
        ".dockerignore": ".git\n.venv\n.hornero/ledger.db*\n",
    }, provides=("container",), requires=("api",)),
    "ci": Component("ci", {
        ".github/workflows/ci.yml": """name: ci
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: '3.11'}
      - run: pip install -e . pytest
      - run: pytest -q
""",
    }, provides=("ci",), requires=("python",)),
    "postgres": Component("postgres", {
        "compose.yaml": """services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: {{package_name}}
      POSTGRES_USER: app
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?required}
    healthcheck: {test: [CMD-SHELL, pg_isready -U app], interval: 5s, timeout: 3s, retries: 10}
""",
        "migrations/001_initial.sql": "CREATE TABLE IF NOT EXISTS app_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);\n",
    }, provides=("database", "migrations"), requires=("project",)),
    "auth": Component("auth", {
        "src/{{package_name}}/auth.py": """\"\"\"Minimal authentication contract; secrets stay in environment-backed adapters.\"\"\"

from dataclasses import dataclass

@dataclass(frozen=True)
class Principal:
    subject: str
    roles: tuple[str, ...] = ()

def authorize(principal: Principal, role: str) -> bool:
    return role in principal.roles
""",
        "tests/test_auth.py": "from {{package_name}}.auth import Principal, authorize\n\ndef test_authorize():\n    assert authorize(Principal('u', ('admin',)), 'admin')\n",
    }, provides=("auth",), requires=("python",)),
    "queue": Component("queue", {
        "src/{{package_name}}/queue.py": """\"\"\"Queue port with a deterministic in-memory adapter.\"\"\"

class MemoryQueue:
    def __init__(self): self._items = []
    def publish(self, item): self._items.append(item)
    def consume(self): return self._items.pop(0)
""",
    }, provides=("queue",), requires=("python",)),
    "observability": Component("observability", {
        "src/{{package_name}}/telemetry.py": """import json
import logging

def event(name: str, **fields: object) -> None:
    logging.getLogger('{{project_slug}}').info(json.dumps({'event': name, **fields}, sort_keys=True))
""",
    }, provides=("observability",), requires=("python",)),
    "iac": Component("iac", {
        "deploy/main.tf": """terraform { required_version = \">= 1.6\" }
variable \"environment\" { type = string }
output \"service_name\" { value = \"{{project_slug}}-${var.environment}\" }
""",
    }, provides=("iac",), requires=("container",)),
    "contracts": Component("contracts", {
        ".hornero/contracts.json": """{
  "service": "{{project_slug}}",
  "version": "1.0.0",
  "operations": [{"name": "health", "method": "GET", "path": "/health"}],
  "events": [{"name": "{{package_name}}.updated", "fields": {"id": "string"}}],
  "models": {"Health": {"status": "string", "service": "string"}}
}
""",
    }, provides=("contracts",), requires=("api",)),
}

BLUEPRINTS = {
    "python-lib": Blueprint(
        "python-lib", "1.0.0", "Python library with tests", ("base", "python")
    ),
    "python-service": Blueprint(
        "python-service", "1.0.0", "Python service with API, Docker and CI",
        ("base", "python", "api", "docker", "ci"),
    ),
    "fullstack": Blueprint(
        "fullstack", "1.0.0", "Python API and JavaScript web application",
        ("base", "python", "api", "web", "docker", "ci"),
    ),
    "production-service": Blueprint(
        "production-service", "1.0.0",
        "Production service with data, auth, queue, telemetry, contracts and IaC",
        (
            "base", "python", "api", "postgres", "auth", "queue",
            "observability", "docker", "iac", "contracts", "ci",
        ),
    ),
}


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _render(text: str, variables: dict[str, str]) -> str:
    missing = sorted(set(_TOKEN.findall(text)) - set(variables))
    if missing:
        raise BlueprintError(f"missing blueprint variables: {', '.join(missing)}")
    return _TOKEN.sub(lambda match: variables[match.group(1)], text)


def variables_for(name: str, supplied: dict[str, str] | None = None) -> dict[str, str]:
    if not _NAME.fullmatch(name):
        raise BlueprintError(
            "project name must start with a letter and contain only letters, "
            "digits, '-' or '_'"
        )
    supplied = dict(supplied or {})
    allowed = {"description"}
    unknown = set(supplied) - allowed
    if unknown:
        raise BlueprintError(f"unknown blueprint variables: {sorted(unknown)}")
    slug = name.lower().replace("_", "-")
    return {
        "project_name": name,
        "project_slug": slug,
        "package_name": slug.replace("-", "_"),
        "description": supplied.get("description", f"{name} project"),
    }


def compose(
    blueprint_name: str,
    variables: dict[str, str],
    extra_components: list[str] | None = None,
    *,
    component_catalog: dict[str, Component] | None = None,
    blueprint_catalog: dict[str, Blueprint] | None = None,
) -> tuple[Blueprint, tuple[str, ...], dict[str, bytes]]:
    component_catalog = component_catalog or COMPONENTS
    blueprint_catalog = blueprint_catalog or BLUEPRINTS
    blueprint = blueprint_catalog.get(blueprint_name)
    if blueprint is None:
        raise BlueprintError(
            f"unknown blueprint {blueprint_name!r}; available: "
            f"{', '.join(sorted(blueprint_catalog))}"
        )
    components = tuple(dict.fromkeys((*blueprint.components, *(extra_components or []))))
    unknown = set(components) - set(component_catalog)
    if unknown:
        raise BlueprintError(f"unknown components: {sorted(unknown)}")
    provided = {
        capability
        for component_name in components
        for capability in component_catalog[component_name].provides
    }
    for component_name in components:
        component = component_catalog[component_name]
        missing = set(component.requires) - provided
        conflicts = set(component.conflicts) & provided
        if missing:
            raise BlueprintError(
                f"component {component_name!r} requires capabilities: {sorted(missing)}"
            )
        if conflicts:
            raise BlueprintError(
                f"component {component_name!r} conflicts with: {sorted(conflicts)}"
            )
    rendered: dict[str, bytes] = {}
    for component_name in components:
        for path_template, content_template in component_catalog[component_name].files.items():
            rel = validate_relative_path(_render(path_template, variables))
            content = _render(content_template, variables).encode("utf-8")
            previous = rendered.get(rel)
            if previous is not None and previous != content:
                raise BlueprintError(
                    f"component collision at {rel}: generated bytes differ"
                )
            rendered[rel] = content
    return blueprint, components, rendered


def resolve_capabilities(
    required: list[str], selected: list[str] | None = None,
    *, component_catalog: dict[str, Component] | None = None,
) -> list[str]:
    """Resolve uniquely provided capabilities without guessing ambiguity."""
    catalog = component_catalog or COMPONENTS
    result = list(dict.fromkeys(selected or []))
    unknown = set(result) - set(catalog)
    if unknown:
        raise BlueprintError(f"unknown components: {sorted(unknown)}")
    while True:
        provided = {
            capability for name in result for capability in catalog[name].provides
        }
        missing = sorted(set(required) - provided)
        for name in result:
            missing.extend(sorted(set(catalog[name].requires) - provided))
        missing = sorted(set(missing))
        if not missing:
            break
        capability = missing[0]
        providers = sorted(
            name for name, component in catalog.items()
            if capability in component.provides and name not in result
        )
        if len(providers) != 1:
            raise BlueprintError(
                f"capability {capability!r} requires exactly one provider; "
                f"candidates: {providers}"
            )
        result.append(providers[0])
    provided = {
        capability for name in result for capability in catalog[name].provides
    }
    for name in result:
        conflicts = set(catalog[name].conflicts) & provided
        if conflicts:
            raise BlueprintError(f"component {name!r} conflicts with {sorted(conflicts)}")
    return result


def _write_lock(
    root: Path,
    blueprint: Blueprint,
    components: tuple[str, ...],
    variables: dict[str, str],
    files: dict[str, bytes],
    *,
    registry: dict[str, str] | None = None,
) -> None:
    lock = {
        "schema": 2,
        "blueprint": blueprint.name,
        "version": blueprint.version,
        "components": list(components),
        "variables": variables,
        "files": {path: _hash_bytes(data) for path, data in sorted(files.items())},
        "base_files": {
            path: base64.b64encode(data).decode("ascii")
            for path, data in sorted(files.items())
        },
        "registry": registry,
    }
    path = root / LOCK_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def create_project(
    destination: Path,
    name: str,
    *,
    blueprint_name: str,
    supplied_variables: dict[str, str] | None = None,
    extra_components: list[str] | None = None,
    git: bool = True,
    commit: bool = False,
    initializer: Callable[[Path], int],
    component_catalog: dict[str, Component] | None = None,
    blueprint_catalog: dict[str, Blueprint] | None = None,
    registry: dict[str, str] | None = None,
) -> Path:
    destination = destination.resolve()
    if destination.exists() and any(destination.iterdir()):
        raise BlueprintError(f"destination is not empty: {destination}")
    created = not destination.exists()
    destination.mkdir(parents=True, exist_ok=True)
    try:
        variables = variables_for(name, supplied_variables)
        blueprint, components, files = compose(
            blueprint_name, variables, extra_components,
            component_catalog=component_catalog,
            blueprint_catalog=blueprint_catalog,
        )
        for rel, content in sorted(files.items()):
            path = contained_path(destination, rel)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        if initializer(destination) != 0:
            raise BlueprintError("Hornero initialization failed")
        _write_lock(
            destination, blueprint, components, variables, files,
            registry=registry,
        )
        if git:
            subprocess.run(
                ["git", "init", "-q", str(destination)], check=True,
                capture_output=True, text=True,
            )
            subprocess.run(
                ["git", "-C", str(destination), "branch", "-M", "main"],
                check=True, capture_output=True, text=True,
            )
            if commit:
                subprocess.run(
                    ["git", "-C", str(destination), "add", "-A"], check=True,
                    capture_output=True, text=True,
                )
                subprocess.run(
                    [
                        "git", "-C", str(destination),
                        "-c", "user.name=Hornero",
                        "-c", "user.email=hornero@invalid",
                        "commit", "-qm", "chore: initialize project",
                    ],
                    check=True, capture_output=True, text=True,
                )
        return destination
    except (OSError, subprocess.SubprocessError) as exc:
        if created:
            shutil.rmtree(destination, ignore_errors=True)
        raise BlueprintError(str(exc)) from exc
    except Exception:
        if created:
            shutil.rmtree(destination, ignore_errors=True)
        raise


def load_lock(root: Path) -> dict:
    path = root / LOCK_PATH
    if not path.is_file():
        raise BlueprintError("no .hornero/blueprint.lock; create with 'hornero new'")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise BlueprintError(f"invalid blueprint lock: {exc}") from exc
    if data.get("schema") not in (1, 2) or not isinstance(data.get("files"), dict):
        raise BlueprintError("unsupported or malformed blueprint lock")
    for rel in data["files"]:
        validate_relative_path(str(rel))
    return data


def status(root: Path) -> dict[str, object]:
    lock = load_lock(root)
    blueprint = BLUEPRINTS.get(str(lock.get("blueprint")))
    version_state = (
        "current"
        if blueprint and blueprint.version == lock.get("version")
        else "behind" if blueprint else "unknown"
    )
    files: dict[str, str] = {}
    for rel, expected in sorted(lock["files"].items()):
        path = contained_path(root, rel)
        if not path.is_file():
            files[rel] = "deleted"
        elif _hash_bytes(path.read_bytes()) == expected:
            files[rel] = "current"
        else:
            files[rel] = "modified"
    return {
        "blueprint": lock.get("blueprint"),
        "installed_version": lock.get("version"),
        "available_version": blueprint.version if blueprint else None,
        "version_state": version_state,
        "files": files,
    }


def upgrade(
    root: Path, *, component_catalog: dict[str, Component],
    blueprint_catalog: dict[str, Blueprint], registry: dict[str, str] | None,
    theirs: set[str] | None = None, ours: set[str] | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    """Three-way base/local/target blueprint upgrade with fail-closed drift."""
    lock = load_lock(root)
    if lock.get("schema") != 2 or not isinstance(lock.get("base_files"), dict):
        raise BlueprintError("blueprint upgrade requires a schema 2 lock")
    theirs = {validate_relative_path(item) for item in (theirs or set())}
    ours = {validate_relative_path(item) for item in (ours or set())}
    if theirs & ours:
        raise BlueprintError(f"paths cannot be both --theirs and --ours: {sorted(theirs & ours)}")
    name = str(lock.get("blueprint"))
    target_blueprint = blueprint_catalog.get(name)
    if target_blueprint is None:
        raise BlueprintError(f"blueprint {name!r} is not available in target registry")
    installed_components = [str(item) for item in lock.get("components", [])]
    extras = [
        item for item in installed_components
        if item not in target_blueprint.components and item in component_catalog
    ]
    _, target_components, target = compose(
        name, {str(k): str(v) for k, v in lock.get("variables", {}).items()}, extras,
        component_catalog=component_catalog, blueprint_catalog=blueprint_catalog,
    )
    try:
        base = {
            str(rel): base64.b64decode(content, validate=True)
            for rel, content in lock["base_files"].items()
        }
    except (ValueError, TypeError) as exc:
        raise BlueprintError(f"invalid blueprint base content: {exc}") from exc
    states: dict[str, str] = {}
    actions: list[tuple[str, str, bytes | None]] = []
    for rel in sorted(set(base) | set(target)):
        path = contained_path(root, rel)
        local = path.read_bytes() if path.is_file() else None
        old = base.get(rel)
        new = target.get(rel)
        resolution = "theirs" if rel in theirs else "ours" if rel in ours else ""
        if new is None:
            if local is None:
                states[rel] = "removed"
            elif local == old or resolution == "theirs":
                states[rel] = "delete"
                actions.append((rel, "delete", None))
            elif resolution == "ours":
                states[rel] = "kept_local"
            else:
                states[rel] = "diverged"
            continue
        if old is None:
            if local is None or resolution == "theirs":
                states[rel] = "add"
                actions.append((rel, "write", new))
            elif local == new:
                states[rel] = "current"
            elif resolution == "ours":
                states[rel] = "kept_local"
            else:
                states[rel] = "diverged"
            continue
        if local == new:
            states[rel] = "current"
        elif local == old:
            states[rel] = "update"
            actions.append((rel, "write", new))
        elif new == old or resolution == "ours":
            states[rel] = "kept_local"
        elif resolution == "theirs":
            states[rel] = "update"
            actions.append((rel, "write", new))
        else:
            states[rel] = "diverged"
    diverged = [rel for rel, state in states.items() if state == "diverged"]
    if diverged:
        raise BlueprintError(
            "blueprint upgrade blocked by diverged files: " + ", ".join(diverged)
        )
    if not dry_run:
        for rel, action, content in actions:
            path = contained_path(root, rel)
            if action == "delete":
                path.unlink(missing_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                assert content is not None
                path.write_bytes(content)
        _write_lock(
            root, target_blueprint, target_components,
            {str(k): str(v) for k, v in lock.get("variables", {}).items()},
            target, registry=registry,
        )
    return {
        "blueprint": name, "from_version": lock.get("version"),
        "to_version": target_blueprint.version, "dry_run": dry_run,
        "files": states,
    }

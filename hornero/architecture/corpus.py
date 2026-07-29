"""Architecture corpus loading, inventory and deterministic reuse resolution."""

from __future__ import annotations

import hashlib
import re
import builtins
from pathlib import Path
from typing import Any

import yaml

from hornero.architecture.model import (
    AUTHORITY_PRECEDENCE,
    PROJECT_SCHEMA,
    ArchitectureError,
    ArchitectureRecord,
    Authority,
    Candidate,
    Evidence,
    ProjectManifest,
    Resolution,
)
from hornero.architecture.profiles import Profile, compose_profiles

_ROLE_KIND = {
    "domains": "domain",
    "capabilities": "capability",
    "components": "component",
    "interfaces": "interface",
    "data": "data",
    "deployments": "deployment",
    "decisions": "decision",
    "patterns": "constraint",
    "quality": "quality",
    "exceptions": "exception",
}
_ID = re.compile(r"^[a-z0-9][a-z0-9._:-]*$")
_LEGACY_POLICIES = {"ignore", "warn", "block"}
_GOVERNANCE_MODES = {"off", "advisory", "enforced"}


def _load_mapping(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ArchitectureError(f"{path}: cannot load YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ArchitectureError(f"{path}: expected a YAML mapping")
    return data


def _strings(value: object, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ArchitectureError(f"{field} must be a list of non-empty strings")
    return tuple(value)


def architecture_root(root: Path) -> Path:
    """Resolve the configured logical architecture root inside the project."""
    root = root.resolve()
    layout = root / ".hornero" / "architecture-layout.yaml"
    if layout.is_file():
        raw = _load_mapping(layout)
        unknown = set(raw) - {"schema", "root"}
        if unknown:
            raise ArchitectureError(
                f"{layout}: unknown layout keys: {sorted(unknown)}"
            )
        if raw.get("schema") != "hornero.architecture.layout/v1":
            raise ArchitectureError(f"{layout}: unsupported layout schema")
        configured = raw.get("root")
        if not isinstance(configured, str) or not configured.strip():
            raise ArchitectureError(f"{layout}: root must be a non-empty path")
        candidate = (root / configured).resolve()
        if not candidate.is_relative_to(root):
            raise ArchitectureError(f"{layout}: architecture root escapes project")
        return candidate
    for relative in ("sdd/architecture", "docs/architecture", "architecture"):
        candidate = root / relative
        if candidate.is_dir():
            return candidate
    return root / "sdd" / "architecture"


def _manifest(path: Path) -> ProjectManifest:
    raw = _load_mapping(path)
    if raw.get("schema") != PROJECT_SCHEMA:
        raise ArchitectureError(f"{path}: unsupported project schema")
    project = raw.get("project")
    stack = raw.get("stack") or {}
    governance = raw.get("governance") or {}
    if not isinstance(project, dict) or not isinstance(stack, dict):
        raise ArchitectureError(f"{path}: project and stack must be mappings")
    if not isinstance(governance, dict):
        raise ArchitectureError(f"{path}: governance must be a mapping")
    project_id = str(project.get("id") or "")
    if not _ID.fullmatch(project_id):
        raise ArchitectureError(f"{path}: invalid project.id {project_id!r}")
    mode = str(governance.get("mode") or "advisory")
    legacy_policy = str(governance.get("legacy_policy") or "warn")
    if mode not in _GOVERNANCE_MODES:
        raise ArchitectureError(f"{path}: unknown governance mode {mode!r}")
    if legacy_policy not in _LEGACY_POLICIES:
        raise ArchitectureError(
            f"{path}: unknown legacy policy {legacy_policy!r}"
        )
    return ProjectManifest(
        path=path,
        project_id=project_id,
        archetypes=_strings(project.get("archetypes"), "project.archetypes"),
        languages=_strings(stack.get("languages"), "stack.languages"),
        frameworks=_strings(stack.get("frameworks"), "stack.frameworks"),
        profiles=_strings(raw.get("profiles"), "profiles"),
        governance_mode=mode,
        legacy_policy=legacy_policy,
        raw=raw,
    )


def _resource_ids(value: object, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ArchitectureError(f"{field} must be a list")
    result: list[str] = []
    for index, item in enumerate(value):
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict) and isinstance(item.get("id"), str):
            result.append(item["id"])
        else:
            raise ArchitectureError(f"{field}[{index}] must identify a resource")
    return tuple(result)


def _record(path: Path, kind: str, root: Path) -> ArchitectureRecord:
    raw = _load_mapping(path)
    schema = f"hornero.architecture.{kind}/v1"
    if raw.get("schema") != schema:
        raise ArchitectureError(f"{path}: expected schema {schema!r}")
    record_id = str(raw.get("id") or "")
    if not _ID.fullmatch(record_id):
        raise ArchitectureError(f"{path}: invalid id {record_id!r}")
    evidence_raw = raw.get("evidence") or []
    if not isinstance(evidence_raw, list):
        raise ArchitectureError(f"{path}: evidence must be a list")
    evidence: list[Evidence] = []
    for index, item in enumerate(evidence_raw):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise ArchitectureError(f"{path}: evidence[{index}] needs path")
        source = (root / item["path"]).resolve()
        if not source.is_relative_to(root.resolve()):
            raise ArchitectureError(f"{path}: evidence[{index}] escapes project")
        digest = ""
        if source.is_file():
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
        evidence.append(Evidence(
            item["path"], str(item.get("locator") or ""),
            str(item.get("sha256") or digest),
        ))
    authority = Authority.DECISION if kind == "decision" else Authority.RECORD
    raw_authority = raw.get("authority")
    if raw_authority:
        try:
            authority = Authority(str(raw_authority))
        except ValueError as exc:
            raise ArchitectureError(f"{path}: unknown authority") from exc
    return ArchitectureRecord(
        record_id=record_id,
        kind=kind,
        title=str(raw.get("title") or record_id),
        path=path,
        owner=str(raw.get("owner") or ""),
        status=str(raw.get("status") or "active"),
        profiles=_strings(raw.get("profiles"), f"{path}: profiles"),
        provides=_strings(raw.get("provides"), f"{path}: provides"),
        interfaces=_strings(raw.get("interfaces"), f"{path}: interfaces"),
        resources=_resource_ids(raw.get("resources"), f"{path}: resources"),
        evidence=tuple(evidence),
        authority=authority,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        raw=raw,
    )


class ArchitectureCorpus:
    """Explicit architecture records under a configurable logical root."""

    def __init__(self, root: Path, *, require_manifest: bool = True) -> None:
        self.root = root.resolve()
        self.architecture_dir = architecture_root(self.root)
        self.profiles: dict[str, Profile]
        manifest_path = self.architecture_dir / "project.yaml"
        if not manifest_path.is_file():
            if require_manifest:
                raise ArchitectureError(
                    "architecture is not initialized; run "
                    "'hornero architecture init --profile NAME'"
                )
            self.project: ProjectManifest | None = None
            self.records: dict[str, ArchitectureRecord] = {}
            self.by_kind: dict[str, list[ArchitectureRecord]] = {}
            self.profiles = {}
            self.unknown_profiles: tuple[str, ...] = ()
            return
        self.project = _manifest(manifest_path)
        records: dict[str, ArchitectureRecord] = {}
        by_kind: dict[str, list[ArchitectureRecord]] = {}
        for role, kind in _ROLE_KIND.items():
            directory = self.architecture_dir / role
            if not directory.is_dir():
                continue
            paths = sorted((*directory.glob("*.yaml"), *directory.glob("*.yml")))
            for path in paths:
                item = _record(path, kind, self.root)
                key = f"{kind}:{item.record_id}"
                if key in records:
                    raise ArchitectureError(f"duplicate architecture record {key}")
                records[key] = item
                by_kind.setdefault(kind, []).append(item)
        self.records = records
        self.by_kind = {
            kind: sorted(items, key=lambda item: item.record_id)
            for kind, items in by_kind.items()
        }
        self.profiles, self.unknown_profiles = compose_profiles(
            self.project.active_profiles, self.architecture_dir / "profiles"
        )

    def get(self, entity_id: str, kind: str | None = None) -> ArchitectureRecord | None:
        if kind:
            return self.records.get(f"{kind}:{entity_id}")
        matches = [
            item for key, item in self.records.items()
            if key.endswith(f":{entity_id}")
        ]
        return matches[0] if len(matches) == 1 else None

    def list(
        self, kind: str | None = None
    ) -> builtins.list[ArchitectureRecord]:
        if kind:
            return list(self.by_kind.get(kind, ()))
        return sorted(self.records.values(), key=lambda item: (item.kind, item.record_id))

    def query(self, text: str) -> builtins.list[ArchitectureRecord]:
        terms = {term.casefold() for term in re.findall(r"[\w:-]+", text)}
        scored: list[tuple[int, ArchitectureRecord]] = []
        for item in self.records.values():
            haystack = " ".join((
                item.record_id, item.title, item.kind, item.owner,
                *item.provides, *item.interfaces, *item.resources,
            )).casefold()
            score = sum(term in haystack for term in terms)
            if score:
                scored.append((score, item))
        return [
            item for _, item in sorted(
                scored, key=lambda pair: (-pair[0], pair[1].kind, pair[1].record_id)
            )
        ]

    def resolve(self, capability_id: str) -> Resolution:
        capability = self.get(capability_id, "capability")
        active_profiles = set(self.project.active_profiles if self.project else ())
        provider_modes: dict[str, str] = {}
        required_interfaces: set[str] = set()
        if capability:
            required_interfaces.update(capability.interfaces)
            requirements = capability.raw.get("requirements")
            if isinstance(requirements, dict):
                raw_interfaces = requirements.get("interfaces")
                required_interfaces.update(
                    _strings(raw_interfaces, f"{capability.path}: requirements.interfaces")
                )
            providers = capability.raw.get("providers") or []
            if not isinstance(providers, list):
                raise ArchitectureError(
                    f"{capability.path}: providers must be a list"
                )
            for provider in providers:
                if isinstance(provider, str):
                    provider_modes[provider] = "reuse"
                elif isinstance(provider, dict) and provider.get("component"):
                    provider_modes[str(provider["component"])] = str(
                        provider.get("mode") or "reuse"
                    )
                else:
                    raise ArchitectureError(
                        f"{capability.path}: provider must identify a component"
                    )
        for registered_component in self.list("component"):
            if capability_id in registered_component.provides:
                provider_modes.setdefault(registered_component.record_id, "reuse")

        eligible: list[Candidate] = []
        excluded: list[Candidate] = []
        for component_id, requested_mode in sorted(provider_modes.items()):
            candidate_component = self.get(component_id, "component")
            if candidate_component is None:
                excluded.append(Candidate(
                    component_id, "needs_human",
                    ("provider record references a missing component",),
                ))
                continue
            reasons: list[str] = []
            if (
                AUTHORITY_PRECEDENCE[candidate_component.authority]
                < AUTHORITY_PRECEDENCE[Authority.RECORD]
            ):
                excluded.append(Candidate(
                    component_id, "needs_human",
                    (
                        "provider authority is "
                        f"{candidate_component.authority.value}, not approved",
                    ),
                    candidate_component.evidence,
                ))
                continue
            if candidate_component.status not in {"active", "experimental"}:
                excluded.append(Candidate(
                    component_id, "needs_human",
                    (f"component status is {candidate_component.status}",),
                    candidate_component.evidence,
                ))
                continue
            missing_profiles = set(candidate_component.profiles) - active_profiles
            if missing_profiles:
                excluded.append(Candidate(
                    component_id, "extend",
                    ("incompatible profiles: " + ", ".join(sorted(missing_profiles)),),
                    candidate_component.evidence,
                ))
                continue
            if not candidate_component.owner:
                excluded.append(Candidate(
                    component_id, "needs_human",
                    ("component has no accountable owner",),
                    candidate_component.evidence,
                ))
                continue
            resolution = requested_mode
            if resolution not in {"reuse", "reuse_with_adapter", "extend"}:
                resolution = "reuse"
            missing_interfaces = (
                required_interfaces - set(candidate_component.interfaces)
            )
            if missing_interfaces and resolution == "reuse":
                resolution = "reuse_with_adapter"
                reasons.append(
                    "adapter required for interfaces: "
                    + ", ".join(sorted(missing_interfaces))
                )
            reasons.append("active provider is compatible with project profiles")
            eligible.append(Candidate(
                component_id, resolution, tuple(reasons),
                candidate_component.evidence,
            ))

        explanation: list[str] = []
        if len(eligible) == 1:
            selected = eligible[0]
            explanation.append(
                f"selected {selected.component}: {selected.resolution}"
            )
            return Resolution(
                capability_id, selected.resolution, selected.component,
                tuple(eligible), tuple(excluded), tuple(explanation),
            )
        if len(eligible) > 1:
            explanation.append(
                "multiple compatible providers require an explicit project decision"
            )
            return Resolution(
                capability_id, "needs_human", None, tuple(eligible),
                tuple(excluded), tuple(explanation),
            )
        if excluded:
            explanation.append(
                "known providers exist but none can be selected safely"
            )
            return Resolution(
                capability_id, "needs_human", None, (), tuple(excluded),
                tuple(explanation),
            )
        explanation.append("no registered provider implements this capability")
        return Resolution(
            capability_id, "new_component", None, (), (), tuple(explanation)
        )


def init_architecture(
    root: Path, profiles: list[str], *, project_id: str | None = None
) -> list[Path]:
    """Add the corpus skeleton without overwriting existing material."""
    directory = architecture_root(root)
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for role in (
        "domains", "capabilities", "components", "interfaces", "data",
        "deployments", "decisions", "patterns", "quality", "profiles",
        "exceptions",
    ):
        (directory / role).mkdir(exist_ok=True)
    manifest = directory / "project.yaml"
    if not manifest.exists():
        archetypes = [
            profile for profile in profiles
            if profile in {
                "monolith", "rest-service", "website", "background-worker",
                "pipeline", "library", "distributed-system",
            }
        ]
        payload = {
            "schema": PROJECT_SCHEMA,
            "project": {
                "id": project_id or re.sub(r"[^a-z0-9._:-]+", "-", root.name.lower()),
                "archetypes": archetypes,
            },
            "stack": {"languages": [], "frameworks": []},
            "profiles": list(dict.fromkeys(profiles)),
            "governance": {"mode": "advisory", "legacy_policy": "warn"},
        }
        manifest.write_text(
            yaml.safe_dump(payload, sort_keys=False), encoding="utf-8"
        )
        written.append(manifest)
    for name, content in {
        "context.md": "# Architecture context\n\nDescribe the system and its boundaries.\n",
        "glossary.md": "# Architecture glossary\n\nDefine canonical domain terms here.\n",
        "principles.md": "# Architecture principles\n\nRecord approved principles here.\n",
    }.items():
        path = directory / name
        if not path.exists():
            path.write_text(content, encoding="utf-8")
            written.append(path)
    return written


def inventory(root: Path, *, propose: bool = False) -> dict[str, Any]:
    """Produce an evidence-backed, non-authoritative repository inventory."""
    from hornero.memory.codegraph import discover_files

    files = discover_files(root)
    languages: set[str] = set()
    components: list[dict[str, Any]] = []
    suffix_language = {
        ".py": "python", ".js": "javascript", ".jsx": "javascript",
        ".ts": "typescript", ".tsx": "typescript", ".go": "go",
        ".rs": "rust", ".java": "java",
    }
    for relative in files:
        path = Path(relative)
        if path.suffix in suffix_language:
            languages.add(suffix_language[path.suffix])
        if (
            path.suffix in suffix_language
            and not relative.startswith(("tests/", "test/"))
            and len(path.parts) <= 4
        ):
            components.append({
                "id": re.sub(r"[^a-z0-9._:-]+", "-", path.with_suffix("").as_posix().lower()),
                "kind": "module",
                "evidence": {
                    "path": relative,
                    "locator": "",
                    "sha256": hashlib.sha256(
                        (root / relative).read_bytes()
                    ).hexdigest(),
                },
                "authority": "inferred",
            })
    result: dict[str, Any] = {
        "schema": "hornero.architecture.inventory/v1",
        "authority": "inferred",
        "languages": sorted(languages),
        "components": components,
    }
    if propose:
        destination = root / "sdd" / "proposals" / "architecture-inventory.yaml"
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            destination.write_text(
                yaml.safe_dump(result, sort_keys=False), encoding="utf-8"
            )
        result["proposal_path"] = destination.relative_to(root).as_posix()
    return result

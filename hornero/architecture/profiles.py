"""Composable built-in and project architecture profiles."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import yaml

from hornero.architecture.model import ArchitectureError


@dataclass(frozen=True)
class Profile:
    name: str
    concerns: tuple[str, ...]
    rules: tuple[str, ...]
    source: str = "builtin"


BUILTIN_PROFILES: dict[str, Profile] = {
    "core": Profile(
        "core",
        ("ownership", "evidence", "dependencies", "public interfaces"),
        ("ARCH-OWNER-001", "ARCH-EVIDENCE-001"),
    ),
    "monolith": Profile(
        "monolith",
        ("module boundaries", "composition root", "shared infrastructure"),
        ("ARCH-MONOLITH-COMPOSITION-001",),
    ),
    "rest-service": Profile(
        "rest-service",
        ("contracts", "authentication", "errors", "idempotency", "timeouts"),
        ("ARCH-REST-CONTRACT-001",),
    ),
    "website": Profile(
        "website",
        ("design system", "accessibility", "navigation", "performance"),
        ("ARCH-WEB-QUALITY-001",),
    ),
    "background-worker": Profile(
        "background-worker",
        ("delivery semantics", "retry", "idempotency", "shutdown"),
        ("ARCH-WORKER-LIFECYCLE-001",),
    ),
    "pipeline": Profile(
        "pipeline",
        ("lineage", "scheduling", "recovery", "reproducibility"),
        ("ARCH-PIPELINE-LINEAGE-001",),
    ),
    "library": Profile(
        "library",
        ("public API", "compatibility", "deprecation", "dependencies"),
        ("ARCH-LIB-COMPAT-001",),
    ),
    "distributed-system": Profile(
        "distributed-system",
        ("ownership", "failure boundaries", "operational budgets"),
        ("ARCH-DISTRIBUTED-FAILURE-001",),
    ),
    "python": Profile(
        "python", ("package boundaries", "runtime lifecycle"), (), "builtin-stack"
    ),
    "aiohttp": Profile(
        "aiohttp", ("application lifecycle", "HTTP views"), (), "builtin-stack"
    ),
    "typescript": Profile(
        "typescript", ("type contracts", "package boundaries"), (), "builtin-stack"
    ),
    "nextjs": Profile(
        "nextjs", ("rendering boundaries", "routing", "bundle budgets"), (),
        "builtin-stack",
    ),
}


def _strings(value: object, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ArchitectureError(f"{field} must be a list of non-empty strings")
    return tuple(value)


def load_custom_profiles(directory: Path) -> dict[str, Profile]:
    result: dict[str, Profile] = {}
    if not directory.is_dir():
        return result
    for path in sorted((*directory.glob("*.yaml"), *directory.glob("*.yml"))):
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise ArchitectureError(f"{path}: invalid YAML: {exc}") from exc
        if not isinstance(raw, dict):
            raise ArchitectureError(f"{path}: profile must be a mapping")
        if raw.get("schema") != "hornero.architecture.profile/v1":
            raise ArchitectureError(f"{path}: unsupported profile schema")
        name = str(raw.get("id") or "")
        if ":" not in name:
            raise ArchitectureError(
                f"{path}: custom profile id must be namespaced (for example acme:web)"
            )
        if name in result:
            raise ArchitectureError(f"duplicate profile id: {name}")
        result[name] = Profile(
            name,
            _strings(raw.get("concerns"), f"{path}: concerns"),
            _strings(raw.get("rules"), f"{path}: rules"),
            path.as_posix(),
        )
    return result


def compose_profiles(
    requested: tuple[str, ...], custom_directory: Path
) -> tuple[dict[str, Profile], tuple[str, ...]]:
    """Resolve profiles without silently substituting unknown names."""
    catalog = {**BUILTIN_PROFILES, **load_custom_profiles(custom_directory)}
    selected: dict[str, Profile] = {}
    unknown: list[str] = []
    for name in dict.fromkeys(("core", *requested)):
        profile = catalog.get(name)
        if profile is None:
            unknown.append(name)
        else:
            selected[name] = profile
    return selected, tuple(unknown)

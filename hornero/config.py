"""``.hornero/config.yaml`` loading (SPEC-001 §4).

Fail-closed: unknown keys raise (catches typos instead of silently ignoring
them). A missing file yields pure defaults. The defaults never include the
``api`` backend — no billed backend by surprise (CLAUDE.md invariant 3).
"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml


class ConfigError(ValueError):
    """Raised for malformed or unknown configuration."""


@dataclass
class DispatchConfig:
    backend_order: list[str] = field(default_factory=lambda: ["mock"])
    cli_command: list[str] = field(default_factory=list)
    timeout_seconds: float = 900.0
    max_output_bytes: int = 1_000_000


@dataclass
class ProviderConfig:
    kind: str
    command: list[str] = field(default_factory=list)
    base_url: str = ""
    model: str = ""
    api_key_env: str = ""
    timeout_seconds: float = 120.0
    max_calls: int = 20
    max_tokens: int = 4096
    retries: int = 1


@dataclass
class AutonomyConfig:
    enabled: bool = False
    max_changes: int = 1
    allowed_risk: list[str] = field(default_factory=lambda: ["low"])
    gates: list[list[str]] = field(default_factory=lambda: [["pytest", "-q"]])
    require_clean_worktree: bool = True
    sandbox_command: list[str] = field(default_factory=list)
    require_sandbox: bool = False


@dataclass
class HorneroConfig:
    signal_source: str = "inbox"
    signal_sources: list[str] = field(default_factory=list)  # [] => [signal_source]
    tracker: str = "repo"
    dispatch: DispatchConfig = field(default_factory=DispatchConfig)
    criterion_allowlist: list[str] = field(
        default_factory=lambda: ["pytest", "ruff", "mypy", "python"]
    )
    models: dict[str, str] = field(default_factory=dict)
    providers: dict[str, ProviderConfig] = field(default_factory=dict)
    autonomy: AutonomyConfig = field(default_factory=AutonomyConfig)
    sdd_upstream: str = ""  # toolkit source (git URL or local path); "" = unset
    sdd_ref: str = "main"


_TOP_KEYS = {
    "signal_source", "signal_sources", "tracker", "dispatch",
    "criterion_allowlist", "models", "providers", "autonomy", "sdd_upstream",
    "sdd_ref",
}
_DISPATCH_KEYS = {
    "backend_order", "cli_command", "timeout_seconds", "max_output_bytes",
}
_PROVIDER_KEYS = {
    "kind", "command", "base_url", "model", "api_key_env",
    "timeout_seconds", "max_calls", "max_tokens", "retries",
}
_AUTONOMY_KEYS = {
    "enabled", "max_changes", "allowed_risk", "gates", "require_clean_worktree",
    "sandbox_command", "require_sandbox",
}
_BACKENDS = {"mock", "cli", "api"}
_SIGNAL_SOURCES = {"inbox", "git"}


def _mapping(value: object, field_name: str) -> dict:
    if not isinstance(value, dict):
        raise ConfigError(f"'{field_name}' must be a mapping")
    return value


def _string(value: object, field_name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ConfigError(f"'{field_name}' must be a string")
    if not allow_empty and not value.strip():
        raise ConfigError(f"'{field_name}' must not be empty")
    return value


def _string_list(value: object, field_name: str) -> list[str]:
    if not isinstance(value, list):
        raise ConfigError(f"'{field_name}' must be a list of strings")
    result: list[str] = []
    for index, item in enumerate(value):
        result.append(_string(item, f"{field_name}[{index}]"))
    if len(result) != len(set(result)):
        raise ConfigError(f"'{field_name}' must not contain duplicates")
    return result


def _positive_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ConfigError(f"'{field_name}' must be a positive number")
    return float(value)


def _nonnegative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ConfigError(f"'{field_name}' must be a non-negative integer")
    return value


def _boolean(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(f"'{field_name}' must be a boolean")
    return value


def load_config(root: Path) -> HorneroConfig:
    """Load config for a repo rooted at ``root``. Missing file => defaults."""
    path = root / ".hornero" / "config.yaml"
    if not path.is_file():
        return HorneroConfig()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: config must be a mapping")
    unknown = set(data) - _TOP_KEYS
    if unknown:
        raise ConfigError(f"{path}: unknown config keys: {sorted(unknown)}")

    cfg = HorneroConfig()
    if "signal_source" in data:
        cfg.signal_source = _string(data["signal_source"], "signal_source")
        if cfg.signal_source not in _SIGNAL_SOURCES:
            raise ConfigError(f"unknown signal source {cfg.signal_source!r}")
    if "signal_sources" in data:
        cfg.signal_sources = _string_list(data["signal_sources"], "signal_sources")
        unknown_sources = set(cfg.signal_sources) - _SIGNAL_SOURCES
        if unknown_sources:
            raise ConfigError(f"unknown signal sources: {sorted(unknown_sources)}")
    if "tracker" in data:
        cfg.tracker = _string(data["tracker"], "tracker")
        if cfg.tracker != "repo":
            raise ConfigError(f"unknown tracker {cfg.tracker!r}")
    if "criterion_allowlist" in data:
        cfg.criterion_allowlist = _string_list(
            data["criterion_allowlist"], "criterion_allowlist"
        )
        if any(any(ch.isspace() for ch in item) for item in cfg.criterion_allowlist):
            raise ConfigError("'criterion_allowlist' entries must be command names")
    if "models" in data:
        models = _mapping(data["models"], "models")
        cfg.models = {
            _string(k, "models key"): _string(v, f"models.{k}")
            for k, v in models.items()
        }
    if "providers" in data:
        providers = _mapping(data["providers"], "providers")
        for name, raw_provider in providers.items():
            provider_name = _string(name, "providers key")
            raw = _mapping(raw_provider, f"providers.{provider_name}")
            unknown_provider_keys = set(raw) - _PROVIDER_KEYS
            if unknown_provider_keys:
                raise ConfigError(
                    f"providers.{provider_name}: unknown keys: "
                    f"{sorted(unknown_provider_keys)}"
                )
            kind = _string(raw.get("kind"), f"providers.{provider_name}.kind")
            if kind not in ("command", "openai_compatible"):
                raise ConfigError(
                    f"providers.{provider_name}.kind: unknown provider {kind!r}"
                )
            provider = ProviderConfig(kind=kind)
            if "command" in raw:
                provider.command = _string_list(
                    raw["command"], f"providers.{provider_name}.command"
                )
            for field_name in ("base_url", "model", "api_key_env"):
                if field_name in raw:
                    setattr(
                        provider, field_name,
                        _string(raw[field_name], f"providers.{provider_name}.{field_name}"),
                    )
            if "timeout_seconds" in raw:
                provider.timeout_seconds = _positive_number(
                    raw["timeout_seconds"],
                    f"providers.{provider_name}.timeout_seconds",
                )
            for field_name in ("max_calls", "max_tokens", "retries"):
                if field_name in raw:
                    setattr(
                        provider, field_name,
                        _nonnegative_int(
                            raw[field_name], f"providers.{provider_name}.{field_name}"
                        ),
                    )
            if kind == "command" and not provider.command:
                raise ConfigError(
                    f"providers.{provider_name}.command must not be empty"
                )
            if kind == "openai_compatible" and (
                not provider.base_url or not provider.model or not provider.api_key_env
            ):
                raise ConfigError(
                    f"providers.{provider_name}: base_url, model and api_key_env "
                    "are required"
                )
            cfg.providers[provider_name] = provider
    if "autonomy" in data:
        raw = _mapping(data["autonomy"], "autonomy")
        unknown_autonomy = set(raw) - _AUTONOMY_KEYS
        if unknown_autonomy:
            raise ConfigError(f"autonomy: unknown keys: {sorted(unknown_autonomy)}")
        if "enabled" in raw:
            cfg.autonomy.enabled = _boolean(raw["enabled"], "autonomy.enabled")
        if "max_changes" in raw:
            cfg.autonomy.max_changes = _nonnegative_int(
                raw["max_changes"], "autonomy.max_changes"
            )
            if cfg.autonomy.max_changes == 0:
                raise ConfigError("'autonomy.max_changes' must be positive")
        if "allowed_risk" in raw:
            cfg.autonomy.allowed_risk = _string_list(
                raw["allowed_risk"], "autonomy.allowed_risk"
            )
            unknown_risk = set(cfg.autonomy.allowed_risk) - {"low", "medium", "high"}
            if unknown_risk:
                raise ConfigError(f"unknown autonomy risks: {sorted(unknown_risk)}")
        if "gates" in raw:
            if not isinstance(raw["gates"], list) or not raw["gates"]:
                raise ConfigError("'autonomy.gates' must be a non-empty list of argv lists")
            cfg.autonomy.gates = [
                _string_list(item, f"autonomy.gates[{index}]")
                for index, item in enumerate(raw["gates"])
            ]
            if any(not gate for gate in cfg.autonomy.gates):
                raise ConfigError("'autonomy.gates' commands must not be empty")
        if "require_clean_worktree" in raw:
            cfg.autonomy.require_clean_worktree = _boolean(
                raw["require_clean_worktree"], "autonomy.require_clean_worktree"
            )
        if "sandbox_command" in raw:
            cfg.autonomy.sandbox_command = _string_list(
                raw["sandbox_command"], "autonomy.sandbox_command"
            )
        if "require_sandbox" in raw:
            cfg.autonomy.require_sandbox = _boolean(
                raw["require_sandbox"], "autonomy.require_sandbox"
            )
        if cfg.autonomy.require_sandbox and not cfg.autonomy.sandbox_command:
            raise ConfigError(
                "'autonomy.sandbox_command' is required when require_sandbox is true"
            )
    if "sdd_upstream" in data:
        cfg.sdd_upstream = _string(
            data["sdd_upstream"], "sdd_upstream", allow_empty=True
        )
    if "sdd_ref" in data:
        cfg.sdd_ref = _string(data["sdd_ref"], "sdd_ref")
    if "dispatch" in data:
        disp = _mapping(data["dispatch"], "dispatch")
        unknown = set(disp) - _DISPATCH_KEYS
        if unknown:
            raise ConfigError(f"{path}: unknown dispatch keys: {sorted(unknown)}")
        if "backend_order" in disp:
            cfg.dispatch.backend_order = _string_list(
                disp["backend_order"], "dispatch.backend_order"
            )
            if not cfg.dispatch.backend_order:
                raise ConfigError("'dispatch.backend_order' must not be empty")
            unknown_backends = set(cfg.dispatch.backend_order) - _BACKENDS
            if unknown_backends:
                raise ConfigError(f"unknown dispatch backends: {sorted(unknown_backends)}")
        if "cli_command" in disp:
            cfg.dispatch.cli_command = _string_list(
                disp["cli_command"], "dispatch.cli_command"
            )
        if "timeout_seconds" in disp:
            cfg.dispatch.timeout_seconds = _positive_number(
                disp["timeout_seconds"], "dispatch.timeout_seconds"
            )
        if "max_output_bytes" in disp:
            value = _nonnegative_int(
                disp["max_output_bytes"], "dispatch.max_output_bytes"
            )
            if value == 0:
                raise ConfigError("'dispatch.max_output_bytes' must be positive")
            cfg.dispatch.max_output_bytes = value
    return cfg

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


@dataclass
class HorneroConfig:
    signal_source: str = "inbox"
    tracker: str = "repo"
    dispatch: DispatchConfig = field(default_factory=DispatchConfig)
    criterion_allowlist: list[str] = field(
        default_factory=lambda: ["pytest", "ruff", "mypy", "python"]
    )
    models: dict[str, str] = field(default_factory=dict)


_TOP_KEYS = {"signal_source", "tracker", "dispatch", "criterion_allowlist", "models"}
_DISPATCH_KEYS = {"backend_order"}


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
        cfg.signal_source = str(data["signal_source"])
    if "tracker" in data:
        cfg.tracker = str(data["tracker"])
    if "criterion_allowlist" in data:
        cfg.criterion_allowlist = [str(x) for x in data["criterion_allowlist"] or []]
    if "models" in data:
        cfg.models = {str(k): str(v) for k, v in (data["models"] or {}).items()}
    if "dispatch" in data:
        disp = data["dispatch"] or {}
        if not isinstance(disp, dict):
            raise ConfigError(f"{path}: 'dispatch' must be a mapping")
        unknown = set(disp) - _DISPATCH_KEYS
        if unknown:
            raise ConfigError(f"{path}: unknown dispatch keys: {sorted(unknown)}")
        if "backend_order" in disp:
            cfg.dispatch.backend_order = [str(x) for x in disp["backend_order"] or []]
    return cfg

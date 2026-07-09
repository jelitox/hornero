"""Shared model resolution for every LLM-driven node (reconciler, wiki,
scribe). One seam — :class:`~hornero.reconciler.draft.LLMPort` — and one
config surface: ``models.<role>``. MVP supports ``fake:<script.json>``
(deterministic FakeLLM); real providers arrive behind the same seam.
"""

from pathlib import Path

from hornero.config import HorneroConfig
from hornero.reconciler.draft import LLMPort
from hornero.reconciler.testing import FakeLLM


def resolve_llm(cfg: HorneroConfig, root: Path, role: str) -> LLMPort | None:
    spec = cfg.models.get(role, "")
    if spec.startswith("fake:"):
        path = Path(spec[len("fake:"):])
        if not path.is_absolute():
            path = root / path
        return FakeLLM.from_file(path)
    return None


def model_name(cfg: HorneroConfig, role: str) -> str:
    return cfg.models.get(role, "") or "(none)"

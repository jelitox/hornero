from __future__ import annotations

import pytest

from hornero.config import ConfigError, load_config


def test_multicoders_config_is_strict_and_bounded(tmp_path):
    state = tmp_path / ".hornero"
    state.mkdir()
    (state / "config.yaml").write_text(
        "multicoders:\n"
        "  command: [python, -m, multicoders]\n"
        "  providers: [codex, claude]\n"
        "  minimum_quorum: 2\n"
        "  timeout_seconds: 30\n"
        "  max_context_bytes: 5000\n"
        "  max_views: 3\n"
    )
    cfg = load_config(tmp_path)
    assert cfg.multicoders.command == ["python", "-m", "multicoders"]
    assert cfg.multicoders.providers == ["codex", "claude"]
    assert cfg.multicoders.minimum_quorum == 2
    assert cfg.multicoders.max_views == 3


def test_multicoders_quorum_cannot_exceed_provider_count(tmp_path):
    state = tmp_path / ".hornero"
    state.mkdir()
    (state / "config.yaml").write_text(
        "multicoders: {providers: [codex], minimum_quorum: 2}\n"
    )
    with pytest.raises(ConfigError, match="exceeds provider count"):
        load_config(tmp_path)

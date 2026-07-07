"""Manifest reader: parse, fallback, glob resolution."""

import json

import pytest

from hornero.sdd_toolkit.manifest import (
    MANIFEST_NAME,
    Manifest,
    ManifestError,
    load_manifest,
    resolve_managed,
)


def _upstream(tmp_path, manifest: dict | None = None):
    (tmp_path / ".claude" / "commands").mkdir(parents=True)
    (tmp_path / ".claude" / "commands" / "sdd-start.md").write_text("start")
    (tmp_path / ".claude" / "commands" / "sdd-task.md").write_text("task")
    (tmp_path / ".claude" / "skills" / "meta-prompting" / "sub").mkdir(parents=True)
    (tmp_path / ".claude" / "skills" / "meta-prompting" / "SKILL.md").write_text("s")
    (tmp_path / ".claude" / "skills" / "meta-prompting" / "sub" / "SKILL.md").write_text("s2")
    (tmp_path / "sdd").mkdir()
    (tmp_path / "sdd" / "WORKFLOW.md").write_text("wf")
    if manifest is not None:
        (tmp_path / MANIFEST_NAME).write_text(json.dumps(manifest))
    return tmp_path


REAL = {
    "name": "sdd-toolkit",
    "version": "2026.07.0",
    "managed": [".claude/commands/*.md", "sdd/WORKFLOW.md"],
    "scaffold": ["sdd/specs/", "sdd/tasks/index/"],
}


def test_load_real_manifest(tmp_path):
    up = _upstream(tmp_path, REAL)
    manifest, fallback = load_manifest(up)
    assert fallback is False
    assert manifest.version == "2026.07.0"
    assert manifest.scaffold == ["sdd/specs/", "sdd/tasks/index/"]


def test_absent_manifest_falls_back_with_flag(tmp_path):
    manifest, fallback = load_manifest(_upstream(tmp_path))
    assert fallback is True
    assert manifest.version == "builtin-fallback"
    assert ".claude/commands/*.md" in manifest.managed


def test_malformed_manifest_raises(tmp_path):
    up = _upstream(tmp_path)
    (up / MANIFEST_NAME).write_text("{not json")
    with pytest.raises(ManifestError, match="invalid JSON"):
        load_manifest(up)
    (up / MANIFEST_NAME).write_text(json.dumps({"name": "x"}))
    with pytest.raises(ManifestError, match="'version'"):
        load_manifest(up)


def test_resolve_managed_globs_sorted(tmp_path):
    up = _upstream(tmp_path, REAL)
    manifest, _ = load_manifest(up)
    assert resolve_managed(up, manifest) == [
        ".claude/commands/sdd-start.md",
        ".claude/commands/sdd-task.md",
        "sdd/WORKFLOW.md",
    ]


def test_resolve_managed_recursive_glob(tmp_path):
    up = _upstream(tmp_path)
    manifest = Manifest("t", "1", managed=[".claude/skills/meta-prompting/**/SKILL.md"])
    resolved = resolve_managed(up, manifest)
    assert ".claude/skills/meta-prompting/sub/SKILL.md" in resolved


def test_missing_pattern_contributes_nothing(tmp_path):
    up = _upstream(tmp_path)
    manifest = Manifest("t", "1", managed=["nope/*.md"])
    assert resolve_managed(up, manifest) == []

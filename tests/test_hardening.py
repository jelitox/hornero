"""SPEC-005 F12 trust-boundary regression tests."""

import json

import pytest

from hornero.config import ConfigError, load_config
from hornero.paths import PathViolation, contained_path, validate_relative_path
from hornero.sdd_toolkit.install import scaffold_dirs
from hornero.sdd_toolkit.lock import load_lock
from hornero.sdd_toolkit.manifest import MANIFEST_NAME, ManifestError, load_manifest


@pytest.mark.parametrize(
    "value",
    ["", "../outside", "a/../../outside", "/tmp/outside", "a\\outside"],
)
def test_relative_path_rejects_unsafe_values(value):
    with pytest.raises(PathViolation):
        validate_relative_path(value)


def test_contained_path_rejects_symlink_escape(tmp_path):
    root = tmp_path / "repo"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "linked").symlink_to(outside, target_is_directory=True)
    with pytest.raises(PathViolation, match="escapes"):
        contained_path(root, "linked/file.md")


def test_manifest_rejects_traversal_before_scaffold(tmp_path):
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    (upstream / MANIFEST_NAME).write_text(
        json.dumps({
            "name": "bad",
            "version": "1",
            "managed": ["../outside/*.md"],
            "scaffold": ["../outside"],
        }),
        encoding="utf-8",
    )
    with pytest.raises(ManifestError, match="unsafe path"):
        load_manifest(upstream)


def test_scaffold_rejects_escape_without_writing(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    with pytest.raises(PathViolation):
        scaffold_dirs(repo, ["../outside"])
    assert not (tmp_path / "outside").exists()


def test_lock_rejects_unsafe_managed_path(tmp_path):
    lock = tmp_path / ".hornero" / "sdd.lock"
    lock.parent.mkdir()
    lock.write_text(json.dumps({
        "upstream": "x",
        "upstream_ref": "main",
        "toolkit_version": "1",
        "upstream_commit": None,
        "synced_at": "",
        "files": {
            "../outside": {
                "upstream_hash": "a",
                "installed_hash": "a",
                "policy": "sync",
            }
        },
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="unsafe managed path"):
        load_lock(tmp_path)


@pytest.mark.parametrize(
    ("yaml_text", "message"),
    [
        ("signal_sources: inbox\n", "list of strings"),
        ("criterion_allowlist: pytest\n", "list of strings"),
        ("models: []\n", "must be a mapping"),
        ("models: {wiki: 12}\n", "models.wiki.*must be a string"),
        ("dispatch: []\n", "must be a mapping"),
        ("dispatch: {backend_order: []}\n", "must not be empty"),
        ("dispatch: {backend_order: [magic]}\n", "unknown dispatch backends"),
        ("signal_sources: [inbox, inbox]\n", "must not contain duplicates"),
        ("tracker: jira\n", "unknown tracker"),
    ],
)
def test_config_rejects_wrong_shapes_and_values(tmp_path, yaml_text, message):
    config = tmp_path / ".hornero" / "config.yaml"
    config.parent.mkdir()
    config.write_text(yaml_text, encoding="utf-8")
    with pytest.raises(ConfigError, match=message):
        load_config(tmp_path)

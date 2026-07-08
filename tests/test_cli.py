"""CLI init/status tests (F1 gate support)."""

import pytest

from hornero.cli import main


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _tree(root):
    return sorted(
        str(p.relative_to(root)) for p in root.rglob("*") if not p.name.startswith("ledger.db")
    )


def test_init_scaffolds_sdd_layout(repo, capsys):
    from hornero.layout import SDD_STATE_DIRS

    assert main(["init"]) == 0
    for d in ("inbox", "processed", "knowledge"):
        assert (repo / ".hornero" / d / ".gitkeep").exists()
    for d in SDD_STATE_DIRS:
        assert (repo / d).is_dir(), d
    assert not (repo / "product").exists()  # SPEC-002 §2: product/ is gone
    assert (repo / ".hornero" / "config.yaml").exists()
    assert (repo / ".hornero" / "ledger.db").exists()
    assert ".hornero/ledger.db" in (repo / ".gitignore").read_text()
    # offline-safe: no upstream configured -> install skipped with a hint
    assert "hornero sdd install" in capsys.readouterr().out


def test_init_no_sdd_flag_skips_hint(repo, capsys):
    assert main(["init", "--no-sdd"]) == 0
    assert "hornero sdd install" not in capsys.readouterr().out


def test_init_idempotent(repo):
    assert main(["init"]) == 0
    before = _tree(repo)
    gitignore = (repo / ".gitignore").read_text()
    assert main(["init"]) == 0
    assert _tree(repo) == before
    assert (repo / ".gitignore").read_text() == gitignore  # no duplicate line


def test_init_preserves_existing_config(repo):
    assert main(["init"]) == 0
    custom = "tracker: repo\n"
    (repo / ".hornero" / "config.yaml").write_text(custom)
    assert main(["init"]) == 0
    assert (repo / ".hornero" / "config.yaml").read_text() == custom


def test_f1_gate_init_then_status_exit_zero(repo, capsys):
    assert main(["init"]) == 0
    assert main(["status"]) == 0
    out = capsys.readouterr().out
    assert "specs: 0 total" in out
    assert "inbox: 0 pending" in out
    assert "knowledge index: absent" in out


def test_status_counts_specs_and_inbox(repo, capsys):
    main(["init"])
    (repo / "sdd" / "specs" / "SPEC-001-x.md").write_text(
        "---\nspec: SPEC-001\ntitle: X\nstatus: approved\n---\n\nBody.\n",
        encoding="utf-8",
    )
    (repo / ".hornero" / "inbox" / "note.md").write_text("hi", encoding="utf-8")
    assert main(["status"]) == 0
    out = capsys.readouterr().out
    assert "specs: 1 total" in out and "approved: 1" in out
    assert "inbox: 1 pending" in out


def test_status_never_mutates(repo):
    main(["init"])
    (repo / ".hornero" / "inbox" / "note.md").write_text("hi", encoding="utf-8")
    before = _tree(repo)
    main(["status"])
    assert _tree(repo) == before


def test_unknown_config_key_fails_closed(repo, capsys):
    main(["init"])
    (repo / ".hornero" / "config.yaml").write_text("tracker: repo\nbananas: 3\n")
    assert main(["status"]) == 1
    assert "unknown config keys" in capsys.readouterr().err


def test_default_config_never_includes_api(repo):
    from hornero.config import load_config

    main(["init"])
    assert load_config(repo).dispatch.backend_order == ["mock"]


def test_all_subcommands_are_wired(repo):
    # F5 closed the last stub: every §10 command now has a real handler.
    from hornero.cli import _stub  # noqa: F401 — kept for future phases
    import hornero.cli as cli
    import inspect

    assert "_stub(" not in inspect.getsource(cli.main)

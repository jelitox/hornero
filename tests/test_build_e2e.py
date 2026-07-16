"""F3 gate: approved fixture spec -> mock backend -> approved→building→review
with a fake PR URL recorded in the ledger."""

import json
import sys

import pytest

from hornero.cli import main
from hornero.lifecycle import Status, parse_spec
from hornero.memory.ledger import Ledger
from hornero.memory.reindex import reindex

APPROVED_SPEC = """---
spec: SPEC-002
title: Weekly digest email
status: approved
kind: new_feature
created: 2026-07-07
sources: [sig-a]
supersedes: []
acceptance_criteria:
  - "pytest tests/digest -q"
---

# SPEC-002 — Weekly digest email

Send a digest.
"""


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    return tmp_path


def _add_spec(repo, text=APPROVED_SPEC, name="SPEC-002-digest.md"):
    (repo / "sdd" / "specs" / name).write_text(text, encoding="utf-8")


def test_f3_gate_approved_to_review_with_fake_pr(repo, capsys):
    _add_spec(repo)
    assert main(["build", "--backend", "mock"]) == 0
    out = capsys.readouterr().out
    assert "SPEC-002: completed -> review" in out

    doc = parse_spec(repo / "sdd" / "specs" / "SPEC-002-digest.md")
    assert doc.status is Status.REVIEW
    log = doc.body[doc.body.index("## Log"):]
    assert "build started" in log and "PR opened: https://example.invalid/pr/SPEC-002-1" in log

    with Ledger(repo / ".hornero" / "ledger.db") as led:
        rows = led.dispatches("SPEC-002")
        assert len(rows) == 1
        assert rows[0]["status"] == "completed"
        assert rows[0]["pr_url"] == "https://example.invalid/pr/SPEC-002-1"
        assert rows[0]["branch"] == "hornero/SPEC-002"


def test_no_approved_specs_is_noop_exit_zero(repo, capsys):
    assert main(["build"]) == 0
    assert "nothing to build" in capsys.readouterr().out
    with Ledger(repo / ".hornero" / "ledger.db") as led:
        assert led.dispatches() == []


def test_explicit_unapproved_id_rejected_all_or_nothing(repo, capsys):
    _add_spec(repo)  # approved
    _add_spec(
        repo,
        APPROVED_SPEC.replace("SPEC-002", "SPEC-003").replace(
            "status: approved", "status: proposed"
        ),
        "SPEC-003-other.md",
    )
    assert main(["build", "SPEC-002", "SPEC-003", "--backend", "mock"]) == 1
    out = capsys.readouterr().out
    assert "not approved: SPEC-003 (status: proposed)" in out
    # nothing transitioned — not even the approved one (all-or-nothing)
    assert parse_spec(repo / "sdd" / "specs" / "SPEC-002-digest.md").status is Status.APPROVED
    with Ledger(repo / ".hornero" / "ledger.db") as led:
        assert led.dispatches() == []


def test_unknown_id_rejected(repo, capsys):
    assert main(["build", "SPEC-999"]) == 1
    assert "unknown spec: SPEC-999" in capsys.readouterr().out


def test_failed_dispatch_goes_needs_human(repo, capsys):
    _add_spec(repo)
    # 'cli' backend is unavailable in this venv => needs_human path
    assert main(["build", "--backend", "cli"]) == 1
    doc = parse_spec(repo / "sdd" / "specs" / "SPEC-002-digest.md")
    assert doc.status is Status.NEEDS_HUMAN
    assert "see trace" in doc.body
    with Ledger(repo / ".hornero" / "ledger.db") as led:
        assert led.dispatches("SPEC-002")[0]["status"] == "needs_human"


def test_invalid_brief_does_not_transition_or_start_run(repo, capsys):
    _add_spec(
        repo,
        APPROVED_SPEC.replace('  - "pytest tests/digest -q"', '  - ""'),
    )
    assert main(["build", "--backend", "mock"]) == 1
    assert "build preflight failed" in capsys.readouterr().out
    assert parse_spec(
        repo / "sdd" / "specs" / "SPEC-002-digest.md"
    ).status is Status.APPROVED
    with Ledger(repo / ".hornero" / "ledger.db") as led:
        assert led._conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
        assert led.dispatches() == []


def test_real_cli_backend_uses_json_protocol_without_shell(repo):
    _add_spec(repo)
    runner = repo / "coding_backend.py"
    runner.write_text(
        "import json, pathlib, sys\n"
        "brief = json.load(sys.stdin)\n"
        "pathlib.Path('brief-seen.json').write_text(json.dumps(brief))\n"
        "print(json.dumps({'status': 'completed', "
        "'pr_url': 'https://example.invalid/pr/cli-1', "
        "'branch': 'hornero/cli-build'}))\n",
        encoding="utf-8",
    )
    config = repo / ".hornero" / "config.yaml"
    config.write_text(
        "dispatch:\n  backend_order: [cli]\n  cli_command:\n"
        f"    - {sys.executable}\n    - {runner}\n"
        "  timeout_seconds: 10\n  max_output_bytes: 10000\n"
        "models: {}\n",
        encoding="utf-8",
    )
    assert main(["build"]) == 0
    brief = json.loads((repo / "brief-seen.json").read_text(encoding="utf-8"))
    assert brief["spec_id"] == "SPEC-002"
    assert parse_spec(
        repo / "sdd" / "specs" / "SPEC-002-digest.md"
    ).status is Status.REVIEW
    with Ledger(repo / ".hornero" / "ledger.db") as led:
        row = led.dispatches("SPEC-002")[0]
        assert row["pr_url"] == "https://example.invalid/pr/cli-1"
        assert row["branch"] == "hornero/cli-build"


def test_stale_graph_blocks_build_before_lifecycle_mutation(repo, capsys):
    _add_spec(repo)
    reindex(repo)
    spec = repo / "sdd" / "specs" / "SPEC-002-digest.md"
    spec.write_text(spec.read_text(encoding="utf-8") + "\nChanged.\n")

    assert main(["build", "--backend", "mock"]) == 1

    assert "graph preflight failed" in capsys.readouterr().out
    assert parse_spec(spec).status is Status.APPROVED
    with Ledger(repo / ".hornero" / "ledger.db") as led:
        assert led.dispatches() == []

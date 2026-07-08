"""F2 gate: fixture inbox (3 notes) -> expected delta set with FakeLLM;
every delta evidence-verified; --dry-run leaves the git diff empty."""

import json
import shutil
import subprocess
from pathlib import Path

from hornero.adapters.inbox import InboxSource
from hornero.cli import main
from hornero.lifecycle import Status, parse_spec
from hornero.memory.ledger import Ledger
from hornero.reconciler.hitl import Decision, ReviewResult
from hornero.reconciler.run import run_reconcile

FIXTURES = Path(__file__).parent / "fixtures" / "inbox_notes"

FIXTURE_SPEC = """---
spec: SPEC-001
title: CSV export
status: approved
kind: new_feature
created: 2026-07-01
sources: [sig-old]
supersedes: []
acceptance_criteria: []
---

# SPEC-001 — CSV export

Export usage as CSV.
"""

NEW_SPEC_PATCH = (
    "---\n"
    "spec: SPEC-XXX\n"
    "title: Monthly usage CSV for finance\n"
    "status: proposed\n"
    "kind: new_feature\n"
    "created: 2026-07-07\n"
    "supersedes: []\n"
    "acceptance_criteria: []\n"
    "---\n\n"
    "# Monthly usage CSV for finance\n\n"
    "Finance needs a monthly CSV of usage to reconcile invoices.\n"
)

CHANGE_DIFF = "@@ -14,1 +14,2 @@\n Export usage as CSV.\n+Include the customer id column.\n"


def _git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
    ).stdout


def _build_repo(tmp_path, monkeypatch):
    """Scaffold a target repo with 3 fixture notes and a FakeLLM script whose
    evidence excerpts are verbatim quotes of those notes."""
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    (tmp_path / "sdd" / "specs" / "SPEC-001-csv-export.md").write_text(
        FIXTURE_SPEC, encoding="utf-8"
    )
    for note in sorted(FIXTURES.glob("note-*.md")):
        shutil.copy(note, tmp_path / ".hornero" / "inbox" / note.name)

    sids = {Path(s["path"]).name: s["signal_id"]
            for s in InboxSource(tmp_path / ".hornero").poll()}

    def delta(kind, title, affected, excerpt, sid, patch, confidence=0.9):
        return {
            "kind": kind, "title": title, "summary": f"{title}.",
            "affected_specs": affected,
            "evidence": [{"signal_id": sid, "excerpt": excerpt, "locator": "L1"}],
            "confidence": confidence, "proposed_patch": patch,
        }

    script = {
        # note-a: a genuinely new requirement
        "reconcile invoices": {"deltas": [delta(
            "new", "Monthly usage CSV for finance", [],
            "export monthly usage as CSV so finance can reconcile invoices",
            sids["note-a.md"], NEW_SPEC_PATCH,
        )]},
        # note-b: a change to SPEC-001 + one fabricated draft that MUST drop
        "customer id column for dedupe": {"deltas": [
            delta("changed", "CSV: add customer id column", ["SPEC-001"],
                  "include the customer id column for dedupe",
                  sids["note-b.md"], CHANGE_DIFF),
            delta("changed", "ghost requirement", ["SPEC-001"],
                  "the export must be XML instead",  # NOT in the note
                  sids["note-b.md"], CHANGE_DIFF, confidence=0.7),
        ]},
        # note-c: already covered => duplicate
        "dashboards someday": {"deltas": [delta(
            "duplicate", "CSV export mentioned again", ["SPEC-001"],
            "exporting usage as CSV again", sids["note-c.md"], "",
        )]},
    }
    (tmp_path / ".hornero" / "fake_llm.json").write_text(
        json.dumps(script, indent=2), encoding="utf-8"
    )
    config = tmp_path / ".hornero" / "config.yaml"
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "models: {}", "models: {reconciler: 'fake:.hornero/fake_llm.json'}"
        ),
        encoding="utf-8",
    )
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.org")
    _git(tmp_path, "config", "user.name", "T")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "baseline")
    return tmp_path


class ScriptedChannel:
    def __init__(self, results):
        self.results = list(results)

    def review(self, delta, diff_text):
        return self.results.pop(0)


def test_f2_gate_dry_run_expected_deltas_and_clean_git(tmp_path, monkeypatch, capsys):
    root = _build_repo(tmp_path, monkeypatch)
    assert main(["reconcile", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "3 delta(s) drafted" in out
    assert "[new] " in out and "Monthly usage CSV for finance" in out
    assert "[changed] " in out and "CSV: add customer id column" in out
    assert "[duplicate] " in out
    assert "ghost requirement" not in out  # fabricated draft never surfaces
    # THE gate assertion: dry-run leaves the working tree clean
    assert _git(root, "status", "--porcelain") == ""


def test_f2_gate_evidence_mismatch_dropped_and_logged(tmp_path, monkeypatch):
    _build_repo(tmp_path, monkeypatch)
    assert main(["reconcile", "--dry-run"]) == 0
    with Ledger(tmp_path / ".hornero" / "ledger.db") as led:
        drops = led.dropped_drafts()
        assert len(drops) == 1
        assert drops[0]["reason"] == "evidence_mismatch"
        assert "ghost requirement" in drops[0]["payload_json"]
        assert len(led.deltas()) == 3  # the survivors, all evidence-verified


def test_no_tty_fail_closed(tmp_path, monkeypatch, capsys):
    root = _build_repo(tmp_path, monkeypatch)
    assert main(["reconcile"]) == 0  # pytest runs without a TTY
    out = capsys.readouterr().out
    assert "no approval channel" in out and "remain proposed" in out
    assert _git(root, "status", "--porcelain") == ""
    assert len(InboxSource(root / ".hornero").poll()) == 3  # nothing acked


def test_approved_deltas_applied_and_acked(tmp_path, monkeypatch):
    root = _build_repo(tmp_path, monkeypatch)
    channel = ScriptedChannel([
        ReviewResult(Decision.APPROVED),  # NEW (note-a)
        ReviewResult(Decision.APPROVED),  # CHANGED (note-b)
        # DUPLICATE (note-c) never presented
    ])
    rc = run_reconcile(root, channel=channel, now=100.0, today="2026-07-07")
    assert rc == 0
    created = parse_spec(next((root / "sdd" / "specs").glob("SPEC-002-*.md")))
    assert created.status is Status.APPROVED
    patched = parse_spec(root / "sdd" / "specs" / "SPEC-001-csv-export.md")
    assert "Include the customer id column." in patched.body
    remaining = [Path(s["path"]).name for s in InboxSource(root / ".hornero").poll()]
    assert remaining == ["note-c.md"]  # duplicate-only signal stays (skipped)
    with Ledger(root / ".hornero" / "ledger.db") as led:
        statuses = {d["delta_id"]: d["status"] for d in led.deltas()}
        assert sorted(statuses.values()) == ["approved", "approved", "proposed"]
        assert led.trace("SPEC-001")["deltas"]  # audit chain exists


def test_no_model_configured_exits_nonzero_before_polling(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    main(["init"])  # default config: models {}
    (tmp_path / ".hornero" / "inbox" / "x.md").write_text("hello", encoding="utf-8")
    assert main(["reconcile"]) == 3
    assert "no model configured" in capsys.readouterr().out
    with Ledger(tmp_path / ".hornero" / "ledger.db") as led:
        assert led._conn.execute("SELECT COUNT(*) c FROM runs").fetchone()["c"] == 0

"""F4 gate: post-"merge" fixture -> reindex -> re-reconciling the same signal
yields DUPLICATE (the loop closes against the BUILT state, not the intent)."""

import json
import shutil
import subprocess
from pathlib import Path

from hornero.adapters.inbox import InboxSource
from hornero.cli import main
from hornero.lifecycle import parse_spec
from hornero.memory.ledger import Ledger
from hornero.memory.reindex import index_staleness
from hornero.reconciler.hitl import Decision, ReviewResult
from hornero.reconciler.run import run_reconcile

FIXTURES = Path(__file__).parent / "fixtures" / "inbox_notes"

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

EXCERPT = "export monthly usage as CSV so finance can reconcile invoices"


class ScriptedChannel:
    def __init__(self, results):
        self.results = list(results)

    def review(self, delta, diff_text):
        return self.results.pop(0)


def _build_repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    shutil.copy(FIXTURES / "note-a.md", tmp_path / ".hornero" / "inbox" / "note-a.md")
    sid = InboxSource(tmp_path / ".hornero").poll()[0]["signal_id"]

    def delta(kind, affected):
        return {
            "kind": kind,
            "title": "Monthly usage CSV for finance"
            if kind == "new" else "CSV for finance mentioned again",
            "summary": "s.",
            "affected_specs": affected,
            "evidence": [{"signal_id": sid, "excerpt": EXCERPT, "locator": "L6"}],
            "confidence": 0.9,
            "proposed_patch": NEW_SPEC_PATCH if kind == "new" else "",
        }

    # Insertion order is the whole trick: once SPEC-001 exists, its corpus
    # line matches first => the model "sees" it is already covered.
    script = {
        "SPEC-001 [approved] Monthly usage CSV for finance": {
            "deltas": [delta("duplicate", ["SPEC-001"])]
        },
        "reconcile invoices": {"deltas": [delta("new", [])]},
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
    return tmp_path, sid


def test_f4_gate_reindex_then_duplicate(tmp_path, monkeypatch):
    root, sid = _build_repo(tmp_path, monkeypatch)

    # Round 1: signal produces a NEW spec, approved and applied ("merged").
    rc = run_reconcile(
        root, channel=ScriptedChannel([ReviewResult(Decision.APPROVED)]),
        now=100.0, today="2026-07-07",
    )
    assert rc == 0
    spec2 = next((root / "product" / "specs").glob("SPEC-001-*.md"))
    assert InboxSource(root / ".hornero").poll() == []  # acked

    # Merge trigger: reindex picks up the built state.
    assert main(["reindex"]) == 0
    assert index_staleness(root) == "fresh"  # ordering guard for round 2

    # Round 2: the SAME signal content arrives again.
    shutil.copy(FIXTURES / "note-a.md", root / ".hornero" / "inbox" / "note-a.md")
    rc = run_reconcile(root, channel=ScriptedChannel([]), now=200.0,
                       today="2026-07-08")
    assert rc == 0

    # Exactly one DUPLICATE, no new spec, ledger records it.
    specs = sorted(p.name for p in (root / "product" / "specs").glob("SPEC-*.md"))
    assert len(specs) == 1 and specs[0].startswith("SPEC-001-")
    with Ledger(root / ".hornero" / "ledger.db") as led:
        dups = [d for d in led.deltas() if d["kind"] == "duplicate"]
        assert len(dups) == 1 and dups[0]["status"] == "proposed"

    # OQ2 telemetry: the covering spec logs the repeat mention.
    doc = parse_spec(spec2)
    assert f"mentioned again in {sid}" in doc.body

    # DUPLICATE never dispatches nor acks: the note stays pending (skipped).
    assert len(InboxSource(root / ".hornero").poll()) == 1


def test_duplicate_comment_failure_is_nonfatal(tmp_path, monkeypatch):
    root, sid = _build_repo(tmp_path, monkeypatch)
    # Force round-2 behavior with a covering spec id that does NOT exist.
    script = {
        "reconcile invoices": {"deltas": [{
            "kind": "duplicate", "title": "dup", "summary": "s.",
            "affected_specs": ["SPEC-099"],
            "evidence": [{"signal_id": sid, "excerpt": EXCERPT, "locator": "L6"}],
            "confidence": 0.5, "proposed_patch": "",
        }]}
    }
    (root / ".hornero" / "fake_llm.json").write_text(json.dumps(script))
    rc = run_reconcile(root, channel=ScriptedChannel([]), now=100.0,
                       today="2026-07-07")
    assert rc == 0  # telemetry failure never breaks the run
    with Ledger(root / ".hornero" / "ledger.db") as led:
        drops = led.dropped_drafts()
        assert any(d["reason"] == "duplicate_comment_failed" for d in drops)


def _git_repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


def test_hook_install_optin_and_idempotent(tmp_path, monkeypatch, capsys):
    root = _git_repo(tmp_path, monkeypatch)
    assert main(["init"]) == 0
    assert not (root / ".git" / "hooks" / "post-merge").exists()  # opt-in only
    assert main(["init", "--hooks"]) == 0
    hook = root / ".git" / "hooks" / "post-merge"
    first = hook.read_text(encoding="utf-8")
    assert "hornero reindex" in first and first.count(">>> hornero") == 1
    assert main(["init", "--hooks"]) == 0  # idempotent re-install
    assert hook.read_text(encoding="utf-8") == first
    assert hook.stat().st_mode & 0o111  # executable


def test_existing_foreign_hook_not_clobbered(tmp_path, monkeypatch, capsys):
    root = _git_repo(tmp_path, monkeypatch)
    hook = root / ".git" / "hooks" / "post-merge"
    hook.write_text("#!/bin/sh\necho mine\n", encoding="utf-8")
    assert main(["init", "--hooks"]) == 1
    assert "refusing to clobber" in capsys.readouterr().err
    assert hook.read_text(encoding="utf-8") == "#!/bin/sh\necho mine\n"


def test_print_ci_hook_writes_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["init", "--print-ci-hook"]) == 0
    out = capsys.readouterr().out
    assert "hornero reindex" in out
    assert not (tmp_path / ".hornero").exists()  # printed, not scaffolded

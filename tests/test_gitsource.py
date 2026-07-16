"""F8 gate: git fixture (3 commits, 1 by "hornero-bot") yields signals
excluding the bot commit; the delta budget queues excess deltas and
re-presents them next run; digests pass through redact()."""

import json
import subprocess

from hornero import watermarks
from hornero.adapters.gitsource import GitSource
from hornero.cli import main
from hornero.memory.ledger import Ledger
from hornero.reconciler.hitl import Decision, ReviewResult
from hornero.reconciler.run import DELTA_BUDGET, run_reconcile
from hornero.reconciler.testing import FakeLLM


class ApproveAll:
    def __init__(self):
        self.seen = []

    def review(self, delta, diff_text):
        self.seen.append(delta)
        return ReviewResult(Decision.REJECTED)  # decisions without writes


def _git(repo, *args, env=None):
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, env=env)


def _repo(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.chdir(repo)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    _git(repo, "config", "user.email", "dev@example.org")
    _git(repo, "config", "user.name", "Dev")
    assert main(["init", "--no-wiki"]) == 0
    return repo


def _commit(repo, name, text, author=None):
    (repo / name).write_text(text, encoding="utf-8")
    _git(repo, "add", "-A")
    args = ["commit", "-qm", f"add {name}: {text.strip()}"]
    if author:
        args += ["--author", author]
    _git(repo, *args)


def test_f8_gate_bot_commits_excluded(tmp_path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)
    _commit(repo, "a.py", "print('feature a')\n")
    _commit(repo, "b.py", "print('bot noise')\n",
            author="hornero-bot <bot@hornero.dev>")
    _commit(repo, "c.py", "print('feature c')\n")
    src = GitSource(repo)
    (sig,) = src.poll()
    from pathlib import Path

    digest = Path(sig["path"]).read_text(encoding="utf-8")
    assert "feature a" in digest and "feature c" in digest
    assert "bot noise" not in digest  # authored by hornero => excluded
    # ack advances the watermark to the window head and moves the digest
    src.ack(sig["signal_id"])
    head = watermarks.get(repo, "gitsource")
    assert head is not None and head["git_head"]
    assert (repo / ".hornero" / "processed" / f"{sig['signal_id']}.md").is_file()
    assert src.poll() == []  # window consumed


def test_poll_is_stable_and_bot_only_window_yields_nothing(tmp_path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)
    _commit(repo, "a.py", "x = 1\n")
    src = GitSource(repo)
    first = src.poll()
    assert first == src.poll()  # re-poll: identical signal, same bytes
    src.ack(first[0]["signal_id"])
    _commit(repo, "b.py", "y = 2\n", author="hornero-bot <bot@hornero.dev>")
    assert src.poll() == []  # only bot commits in the window


def test_digest_is_redacted(tmp_path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)
    token = "ghp_" + "a1B2c3D4" * 4
    _commit(repo, "a.py", "x = 1\n")
    # amend-style: commit message carrying a secret
    (repo / "b.py").write_text("y = 2\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", f"oops leaked {token}")
    (sig,) = GitSource(repo).poll()
    from pathlib import Path

    digest = Path(sig["path"]).read_text(encoding="utf-8")
    assert token not in digest and "[REDACTED:GitHub token]" in digest


def _delta_json(n, sid, excerpt):
    return json.dumps({"deltas": [
        {"kind": "new", "title": f"Feature {i}", "summary": "s",
         "affected_specs": [],
         "evidence": [{"signal_id": sid, "excerpt": excerpt, "locator": "L1"}],
         "confidence": 0.9 - i * 0.01,
         "proposed_patch": "prose"} for i in range(n)
    ]})


def test_f8_gate_budget_queues_and_represents(tmp_path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)
    marker = "seven features requested"
    (repo / ".hornero" / "inbox" / "note.md").write_text(marker, encoding="utf-8")
    from hornero.adapters.inbox import InboxSource

    sid = InboxSource(repo / ".hornero").poll()[0]["signal_id"]
    llm = FakeLLM({marker: _delta_json(7, sid, marker)})
    ch = ApproveAll()
    assert run_reconcile(repo, llm=llm, channel=ch, now=1.0, today="2026-07-08") == 0
    assert len(ch.seen) == DELTA_BUDGET  # 5 presented
    with Ledger(repo / ".hornero" / "ledger.db") as led:
        queued = led.queued_deltas()
    assert len(queued) == 2  # excess queued, not dropped
    # A scheduled/no-TTY pass may surface queue debt but must not consume it.
    assert run_reconcile(
        repo, llm=FakeLLM({}), channel=None, now=1.5, today="2026-07-08"
    ) == 0
    with Ledger(repo / ".hornero" / "ledger.db") as led:
        still_queued = led.queued_deltas()
        assert len(still_queued) == 2
        assert all(row["presented_count"] == 1 for row in still_queued)
    # next run: nothing new to draft; the 2 queued are re-presented
    ch2 = ApproveAll()
    llm2 = FakeLLM({})  # any drafting call would raise
    assert run_reconcile(repo, llm=llm2, channel=ch2, now=2.0, today="2026-07-08") == 0
    assert sorted(d.title for d in ch2.seen) == sorted(
        d["title"] for d in queued
    )
    with Ledger(repo / ".hornero" / "ledger.db") as led:
        assert led.queued_deltas() == []  # decisions consumed the queue


def test_git_source_end_to_end_reconcile(tmp_path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)
    (repo / ".hornero" / "config.yaml").write_text(
        "signal_sources: [git]\n", encoding="utf-8"
    )
    _commit(repo, "exporter.py", "def export(): pass\n")
    excerpt = "add exporter.py: def export(): pass"
    sid = GitSource(repo).poll()[0]["signal_id"]
    llm = FakeLLM({"Git activity digest": json.dumps({"deltas": [{
        "kind": "new", "title": "Formalize exporter", "summary": "shipped unspec'd",
        "affected_specs": [],
        "evidence": [{"signal_id": sid, "excerpt": excerpt,
                      "locator": "commit"}],
        "confidence": 0.8, "proposed_patch": "prose"}]})})
    ch = ApproveAll()
    assert run_reconcile(repo, llm=llm, channel=ch, now=1.0, today="2026-07-08") == 0
    assert [d.title for d in ch.seen] == ["Formalize exporter"]
    assert ch.seen[0].evidence[0].excerpt == excerpt  # verbatim vs digest


def test_unknown_signal_source_fails_closed(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path, monkeypatch)
    (repo / ".hornero" / "config.yaml").write_text(
        "signal_sources: [inbox, carrier-pigeon]\n", encoding="utf-8"
    )
    llm = FakeLLM({})
    assert run_reconcile(repo, llm=llm, channel=ApproveAll()) == 1

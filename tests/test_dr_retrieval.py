"""F11 gate: a signal re-proposing a DR-rejected approach surfaces the DR in
the delta preview; wiki quickstart links the decision history."""

import json

from hornero.cli import main
from hornero.reconciler.hitl import Decision, ReviewResult
from hornero.reconciler.run import run_reconcile
from hornero.reconciler.testing import FakeLLM

DR = """---
dr: DR-014
run_id: r-9-spec-001
spec: SPEC-001
date: 2026-07-01
actor: dispatch:mock
outcome: completed
---

# DR-014 — CSV parser choice

## Alternatives considered and rejected

- Streaming csv parser: rejected because quoted newlines break the chunker
  and silently corrupt exports. [e#12-e#18]
"""


class Capture:
    def __init__(self):
        self.previews = []

    def review(self, delta, diff_text):
        self.previews.append(diff_text)
        return ReviewResult(Decision.REJECTED)


def test_f11_gate_rejected_approach_surfaces_dr(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["init", "--no-wiki"]) == 0
    (tmp_path / "sdd" / "decisions" / "DR-014-csv-parser.md").write_text(
        DR, encoding="utf-8"
    )
    note = "we should switch to a streaming csv parser for the exports"
    (tmp_path / ".hornero" / "inbox" / "note.md").write_text(note, encoding="utf-8")
    from hornero.adapters.inbox import InboxSource

    sid = InboxSource(tmp_path / ".hornero").poll()[0]["signal_id"]
    llm = FakeLLM({note: json.dumps({"deltas": [{
        "kind": "new", "title": "Streaming csv parser",
        "summary": "switch exports to a streaming csv parser",
        "affected_specs": [],
        "evidence": [{"signal_id": sid, "excerpt": note, "locator": "L1"}],
        "confidence": 0.9, "proposed_patch": "prose"}]})})
    ch = Capture()
    assert run_reconcile(tmp_path, llm=llm, channel=ch, now=1.0,
                         today="2026-07-08") == 0
    (preview,) = ch.previews
    assert "[memory] DR-014-csv-parser.md" in preview  # the human sees it
    assert preview.index("[memory]") < preview.index("prose")  # before patch


def test_no_dr_no_annotation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["init", "--no-wiki"]) == 0
    note = "add a pdf export button"
    (tmp_path / ".hornero" / "inbox" / "note.md").write_text(note, encoding="utf-8")
    from hornero.adapters.inbox import InboxSource

    sid = InboxSource(tmp_path / ".hornero").poll()[0]["signal_id"]
    llm = FakeLLM({note: json.dumps({"deltas": [{
        "kind": "new", "title": "PDF export", "summary": "pdf export button",
        "affected_specs": [],
        "evidence": [{"signal_id": sid, "excerpt": note, "locator": "L1"}],
        "confidence": 0.9, "proposed_patch": "prose"}]})})
    ch = Capture()
    assert run_reconcile(tmp_path, llm=llm, channel=ch, now=1.0,
                         today="2026-07-08") == 0
    assert "[memory]" not in ch.previews[0]


def test_wiki_quickstart_links_decision_history(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["init", "--no-wiki"]) == 0
    from hornero.wiki import wiki_init

    body = ("A repo with enough content to clear the anti-stub bar and then "
            "some, including change-oriented guidance for the next agent.")
    pages = json.dumps({"pages": [{"path": "quickstart.md",
                                   "content": f"# Q\n\n{body}"}]})
    assert wiki_init(tmp_path, FakeLLM({"Top-level tree": pages})) == 0
    text = (tmp_path / "wiki" / "quickstart.md").read_text(encoding="utf-8")
    assert "sdd/decisions" in text and "Decision history" in text

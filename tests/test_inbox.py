"""F1 gate tests: InboxSource (SPEC-001 §7)."""

from hornero.adapters.inbox import InboxSource
from hornero.ports import SignalSource


def _inbox(tmp_path, files: dict[str, str]):
    (tmp_path / "inbox").mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (tmp_path / "inbox" / name).write_text(content, encoding="utf-8")
    return InboxSource(tmp_path)


def test_poll_lists_supported_files_deterministically(tmp_path):
    source = _inbox(
        tmp_path,
        {"b-notes.md": "notes", "a-call.vtt": "WEBVTT", "c-doc.txt": "doc"},
    )
    signals = source.poll()
    assert [s["kind"] for s in signals] == ["transcript", "meeting_notes", "document"]
    assert [s["path"].rsplit("/", 1)[-1] for s in signals] == [
        "a-call.vtt", "b-notes.md", "c-doc.txt",
    ]


def test_signal_ids_stable_across_polls(tmp_path):
    source = _inbox(tmp_path, {"n.md": "same content"})
    first = source.poll()[0]["signal_id"]
    second = source.poll()[0]["signal_id"]
    assert first == second
    assert first.startswith("sig-20")


def test_different_content_different_id(tmp_path):
    source = _inbox(tmp_path, {"a.md": "one", "b.md": "two"})
    ids = {s["signal_id"] for s in source.poll()}
    assert len(ids) == 2


def test_ack_moves_to_processed_and_is_idempotent(tmp_path):
    source = _inbox(tmp_path, {"n.md": "note"})
    sid = source.poll()[0]["signal_id"]
    source.ack(sid)
    assert source.poll() == []
    assert (tmp_path / "processed" / "n.md").read_text(encoding="utf-8") == "note"
    source.ack(sid)  # double-ack: silent no-op
    source.ack("sig-unknown-000000")  # unknown id: silent no-op


def test_ack_collision_gets_deterministic_suffix(tmp_path):
    source = _inbox(tmp_path, {"n.md": "v2"})
    (tmp_path / "processed").mkdir()
    (tmp_path / "processed" / "n.md").write_text("v1", encoding="utf-8")
    source.ack(source.poll()[0]["signal_id"])
    assert (tmp_path / "processed" / "n-1.md").read_text(encoding="utf-8") == "v2"


def test_unsupported_extension_ignored(tmp_path):
    source = _inbox(tmp_path, {"pic.png": "x", "notes.md": "y"})
    signals = source.poll()
    assert len(signals) == 1 and signals[0]["kind"] == "meeting_notes"
    assert (tmp_path / "inbox" / "pic.png").exists()  # not deleted


def test_missing_inbox_dir_returns_empty(tmp_path):
    assert InboxSource(tmp_path).poll() == []


def test_protocol_conformance(tmp_path):
    assert isinstance(InboxSource(tmp_path), SignalSource)

"""SPEC-005 F15 document normalization and provenance sidecars."""

import json
import zipfile

from hornero.adapters.inbox import InboxSource
from hornero.cli import main
from hornero.ingest import MAX_DOCUMENT_BYTES


def _repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    return tmp_path


def test_ingest_html_redacts_and_writes_provenance(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, monkeypatch)
    document = tmp_path / "meeting.html"
    secret = "sk-abcdefghijklmnopqrstuvwx"
    document.write_text(
        f"<h1>Meeting</h1><p>Need audit export {secret}</p>"
        "<script>ignore()</script>", encoding="utf-8"
    )
    assert main(["ingest", str(document), "--kind", "meeting_notes"]) == 0
    normalized = next((root / ".hornero" / "inbox").glob("meeting-*.md"))
    text = normalized.read_text(encoding="utf-8")
    assert "Need audit export" in text and "ignore()" not in text
    assert secret not in text and "[REDACTED:secret key" in text
    sidecar = normalized.with_suffix(".source.json")
    metadata = json.loads(sidecar.read_text(encoding="utf-8"))
    assert metadata["extractor"] == "html.parser"
    assert metadata["normalized"] == normalized.name
    assert "ingested:" in capsys.readouterr().out


def test_ingest_json_yaml_and_docx(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch)
    json_doc = tmp_path / "requirements.json"
    json_doc.write_text('{"z": 1, "requirement": "export"}', encoding="utf-8")
    yaml_doc = tmp_path / "controls.yaml"
    yaml_doc.write_text("controls:\n  - SOC2\n", encoding="utf-8")
    docx = tmp_path / "brief.docx"
    with zipfile.ZipFile(docx, "w") as archive:
        archive.writestr(
            "word/document.xml",
            '<?xml version="1.0"?><w:document '
            'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:body><w:p><w:r><w:t>Build secure login</w:t></w:r></w:p>'
            '</w:body></w:document>',
        )
    assert main(["ingest", str(json_doc), str(yaml_doc), str(docx)]) == 0
    contents = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (root / ".hornero" / "inbox").glob("*.md")
    )
    assert "requirement" in contents and "SOC2" in contents
    assert "Build secure login" in contents


def test_ack_moves_ingest_sidecar_with_normalized_signal(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch)
    document = tmp_path / "note.txt"
    document.write_text("New retention requirement", encoding="utf-8")
    assert main(["ingest", str(document)]) == 0
    source = InboxSource(root / ".hornero")
    signal = source.poll()[0]
    source.ack(signal["signal_id"])
    processed = root / ".hornero" / "processed"
    assert list(processed.glob("note-*.md"))
    assert list(processed.glob("note-*.source.json"))


def test_ingest_rejects_unsupported_and_oversized(tmp_path, monkeypatch, capsys):
    _repo(tmp_path, monkeypatch)
    unsupported = tmp_path / "binary.bin"
    unsupported.write_bytes(b"abc")
    assert main(["ingest", str(unsupported)]) == 1
    assert "unsupported document type" in capsys.readouterr().err
    oversized = tmp_path / "large.txt"
    with oversized.open("wb") as stream:
        stream.truncate(MAX_DOCUMENT_BYTES + 1)
    assert main(["ingest", str(oversized)]) == 1
    assert "document exceeds" in capsys.readouterr().err

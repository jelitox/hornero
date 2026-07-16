"""Safe document normalization into Hornero's filesystem inbox."""

from __future__ import annotations

import hashlib
import html
import json
import re
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

import yaml

from hornero.redact import redact

MAX_DOCUMENT_BYTES = 10 * 1024 * 1024


class IngestError(RuntimeError):
    pass


class _HTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._ignored = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style"):
            self._ignored += 1
        elif tag in ("p", "br", "div", "li", "h1", "h2", "h3", "tr"):
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._ignored:
            self._ignored -= 1
        elif tag in ("p", "div", "li", "h1", "h2", "h3", "tr"):
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._ignored:
            self.parts.append(data)

    def text(self) -> str:
        lines = [" ".join(line.split()) for line in "".join(self.parts).splitlines()]
        return "\n".join(line for line in lines if line)


def _docx_text(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            raw = archive.read("word/document.xml")
    except (KeyError, OSError, zipfile.BadZipFile) as exc:
        raise IngestError(f"invalid DOCX document: {path}") from exc
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError as exc:
        raise IngestError(f"invalid DOCX XML: {path}") from exc
    paragraphs: list[str] = []
    for paragraph in root.iter():
        if paragraph.tag.endswith("}p"):
            text = "".join(
                child.text or "" for child in paragraph.iter()
                if child.tag.endswith("}t")
            ).strip()
            if text:
                paragraphs.append(text)
    return "\n\n".join(paragraphs)


def _pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader  # type: ignore[import-not-found]
    except ImportError as exc:
        raise IngestError(
            "PDF extraction requires the optional 'pypdf' package"
        ) from exc
    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            raise IngestError(f"encrypted PDF is not supported: {path}")
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    except IngestError:
        raise
    except Exception as exc:
        raise IngestError(f"could not extract PDF: {path}: {exc}") from exc


def extract(path: Path) -> tuple[str, str]:
    suffix = path.suffix.lower()
    if suffix in (".md", ".txt", ".vtt"):
        return path.read_text(encoding="utf-8", errors="replace"), "text"
    if suffix in (".html", ".htm"):
        parser = _HTMLText()
        parser.feed(path.read_text(encoding="utf-8", errors="replace"))
        return parser.text(), "html.parser"
    if suffix == ".json":
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise IngestError(f"invalid JSON document: {path}: {exc}") from exc
        return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False), "json"
    if suffix in (".yaml", ".yml"):
        try:
            value = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise IngestError(f"invalid YAML document: {path}: {exc}") from exc
        return yaml.safe_dump(value, sort_keys=True, allow_unicode=True), "yaml"
    if suffix == ".docx":
        return _docx_text(path), "docx-xml"
    if suffix == ".pdf":
        return _pdf_text(path), "pypdf"
    raise IngestError(f"unsupported document type {suffix or '(none)'}: {path}")


def ingest(root: Path, source: Path, *, kind: str = "document") -> Path:
    source = source.expanduser().resolve()
    if not source.is_file():
        raise IngestError(f"document not found: {source}")
    size = source.stat().st_size
    if size > MAX_DOCUMENT_BYTES:
        raise IngestError(
            f"document exceeds {MAX_DOCUMENT_BYTES} bytes: {source} ({size})"
        )
    raw = source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    text, extractor = extract(source)
    text = redact(html.unescape(text)).strip()
    if not text:
        raise IngestError(f"document contains no extractable text: {source}")
    slug = re.sub(r"[^a-z0-9]+", "-", source.stem.lower()).strip("-") or "document"
    basename = f"{slug}-{digest[:10]}"
    inbox = root / ".hornero" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    destination = inbox / f"{basename}.md"
    normalized = (
        f"# Imported document: {source.name}\n\n"
        f"- kind: {kind}\n"
        f"- source_sha256: {digest}\n"
        f"- extractor: {extractor}\n\n"
        f"## Content\n\n{text}\n"
    )
    destination.write_text(normalized, encoding="utf-8")
    sidecar = inbox / f"{basename}.source.json"
    sidecar.write_text(json.dumps({
        "schema": 1,
        "source_name": source.name,
        "source_path": str(source),
        "source_sha256": digest,
        "source_bytes": size,
        "extractor": extractor,
        "kind": kind,
        "normalized": destination.name,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination

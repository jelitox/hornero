"""Local code knowledge graph: scanner, SQLite plane, CLI, HTML report."""

from pathlib import Path

from hornero.cli import main
from hornero.memory import codegraph
from hornero.memory.knowledge import CodeGraphKnowledge, open_knowledge
from hornero.memory.reindex import reindex


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_scanner_builds_file_dir_and_import_edges(tmp_path):
    _write(
        tmp_path,
        "pkg/a.py",
        '"""Module A."""\nfrom pkg.b import thing\n\n\ndef run(x):\n    """Run A."""\n    return thing(x)\n',
    )
    _write(tmp_path, "pkg/b.py", '"""Module B."""\ndef thing(x):\n    return x\n')
    _write(tmp_path, "README.md", "# Project\n\nDocs.")
    scan = codegraph.scan(tmp_path)
    ids = {p.concept_id for p in scan.pages}
    assert "file:pkg/a.py" in ids
    assert "dir:pkg" in ids
    assert ("dir:pkg", "file:pkg/a.py", "contains") in scan.edges
    assert ("file:pkg/a.py", "file:pkg/b.py", "references") in scan.edges
    page = next(p for p in scan.pages if p.concept_id == "file:pkg/a.py")
    assert "def run(x): Run A." in page.body


def test_reindex_writes_graph_db_and_html_report(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    _write(tmp_path, "horneroish.py", '"""Tiny module."""\nVALUE = 1\n')
    manifest = reindex(tmp_path)
    assert codegraph.db_path(tmp_path).is_file()
    assert codegraph.html_report_path(tmp_path).is_file()
    assert manifest["layers"]["codegraph"] is True
    assert manifest["graph"]["pages"] >= 1
    assert manifest["graph"]["html_report"] == "sdd/reports/knowledge-graph.html"


def test_graph_search_page_related_and_open_knowledge(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    _write(tmp_path, "pkg/a.py", '"""Importer."""\nimport pkg.b\n')
    _write(tmp_path, "pkg/b.py", '"""Target module."""\n')
    reindex(tmp_path)

    hits = codegraph.search(tmp_path, "Target module", limit=3)
    assert hits and hits[0].concept_id == "file:pkg/b.py"
    assert codegraph.get_page(tmp_path, "file:pkg/b.py") is not None
    assert any(
        row["concept_id"] == "file:pkg/b.py"
        for row in codegraph.related(tmp_path, "file:pkg/a.py", rel="references")
    )
    assert isinstance(open_knowledge(tmp_path), CodeGraphKnowledge)

    assert main(["knowledge", "query", "Target module"]) == 0
    assert "file:pkg/b.py" in capsys.readouterr().out
    assert main(["knowledge", "page", "file:pkg/b.py", "--max-chars", "120"]) == 0
    assert "Target module" in capsys.readouterr().out
    assert main(["knowledge", "related", "file:pkg/a.py", "--rel", "references"]) == 0
    assert "file:pkg/b.py" in capsys.readouterr().out
    assert main(["knowledge", "status"]) == 0
    assert "knowledge graph:" in capsys.readouterr().out

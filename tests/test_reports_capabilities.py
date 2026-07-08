"""Capabilities report: content, escaping, determinism, offline purity."""

import re

from hornero.reports.capabilities import generate
from hornero.reports.engine import build_context

SPEC_TMPL = """---
spec: {sid}
title: {title}
status: {status}
kind: new_feature
created: 2026-07-01
sources: [sig-x]
supersedes: []
acceptance_criteria: []
---

# {sid}

{body}
"""


def _repo(tmp_path):
    specs = tmp_path / "sdd" / "specs"
    specs.mkdir(parents=True)
    (tmp_path / ".hornero").mkdir()
    (specs / "SPEC-001-csv.md").write_text(
        SPEC_TMPL.format(sid="SPEC-001", title="CSV export", status="done",
                         body="Implemented in src/exporter module."),
        encoding="utf-8",
    )
    (specs / "SPEC-002-digest.md").write_text(
        SPEC_TMPL.format(sid="SPEC-002", title="Weekly digest", status="proposed",
                         body="No component yet."),
        encoding="utf-8",
    )
    (specs / "SPEC-003-xss.md").write_text(
        SPEC_TMPL.format(sid="SPEC-003", title="<script>alert(1)</script>",
                         status="done", body="Also in src/exporter."),
        encoding="utf-8",
    )
    return tmp_path


def test_every_done_spec_listed_and_grouped(tmp_path):
    html = generate(build_context(_repo(tmp_path)))
    assert "SPEC-001" in html and "SPEC-003" in html and "SPEC-002" in html
    assert "<h2>exporter</h2>" in html and "<h2>general</h2>" in html
    assert "2 shipped" in html


def test_relative_links(tmp_path):
    html = generate(build_context(_repo(tmp_path)))
    assert 'href="../specs/SPEC-001-csv.md"' in html


def test_html_escaping(tmp_path):
    html = generate(build_context(_repo(tmp_path)))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_no_external_resources(tmp_path):
    html = generate(build_context(_repo(tmp_path)))
    for attr in re.findall(r'(?:src|href)="([^"]+)"', html):
        assert not attr.startswith(("http://", "https://", "//")), attr


def test_deterministic_output(tmp_path):
    root = _repo(tmp_path)
    assert generate(build_context(root)) == generate(build_context(root))


def test_empty_corpus_renders(tmp_path):
    (tmp_path / "sdd" / "specs").mkdir(parents=True)
    (tmp_path / ".hornero").mkdir()
    html = generate(build_context(tmp_path))
    assert "No specs yet" in html

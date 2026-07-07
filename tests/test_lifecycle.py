"""F1 gate tests: spec lifecycle (SPEC-001 §5)."""

import pytest

from hornero.lifecycle import (
    IllegalTransition,
    SpecCorpus,
    SpecParseError,
    Status,
    TRANSITIONS,
    parse_spec,
    transition,
    write_spec,
)

SPEC_TEXT = """---
spec: SPEC-004
title: Export monthly usage as CSV
status: proposed            # proposed|approved|building|review|done
kind: new_feature
created: 2026-07-06
sources: [sig-20260706-a1]
supersedes: []
owner: someone@example.org
acceptance_criteria:
  - "pytest tests/export/test_csv.py -q"
  - "manual: CSV opens correctly in LibreOffice"
---

# SPEC-004 — Export monthly usage as CSV

Body text.

## Log

- 2026-07-06 — drafted.
"""


def _write(tmp_path, name="SPEC-004-export-csv.md", text=SPEC_TEXT):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_roundtrip_byte_identical(tmp_path):
    p = _write(tmp_path)
    doc = parse_spec(p)
    write_spec(doc)
    assert p.read_text(encoding="utf-8") == SPEC_TEXT
    # extra keys (owner) and comments survive untouched
    assert "owner: someone@example.org" in p.read_text(encoding="utf-8")


def test_parse_extracts_contract_fields(tmp_path):
    doc = parse_spec(_write(tmp_path))
    assert doc.spec_id == "SPEC-004"
    assert doc.status is Status.PROPOSED
    assert doc.sources == ["sig-20260706-a1"]
    assert doc.acceptance_criteria[0].startswith("pytest ")
    assert "# SPEC-004" in doc.body


def test_legal_path_proposed_to_done(tmp_path):
    doc = parse_spec(_write(tmp_path))
    for target in ("approved", "building", "review", "done"):
        doc = transition(doc, target)
    assert doc.status is Status.DONE
    write_spec(doc)
    text = doc.path.read_text(encoding="utf-8")
    assert "status: done            # proposed|approved|building|review|done" in text


def test_transition_touches_only_status_line(tmp_path):
    doc = parse_spec(_write(tmp_path))
    moved = transition(doc, "approved")
    diff = [
        (a, b)
        for a, b in zip(
            doc.raw_frontmatter.splitlines(), moved.raw_frontmatter.splitlines()
        )
        if a != b
    ]
    assert len(diff) == 1 and diff[0][0].startswith("status:")


def test_illegal_transition_raises(tmp_path):
    doc = parse_spec(_write(tmp_path))
    with pytest.raises(IllegalTransition):
        transition(doc, "building")  # proposed -> building is not an edge


def test_terminal_states_have_no_exits():
    assert TRANSITIONS[Status.REJECTED] == set()
    assert TRANSITIONS[Status.OBSOLETE] == set()


def test_obsolete_reachable_from_every_nonterminal(tmp_path):
    for status in Status:
        if status in (Status.REJECTED, Status.OBSOLETE):
            continue
        assert Status.OBSOLETE in TRANSITIONS[status], status


def test_needs_human_reenters_approved(tmp_path):
    assert Status.APPROVED in TRANSITIONS[Status.NEEDS_HUMAN]


def test_unknown_status_fails_closed(tmp_path):
    p = _write(tmp_path, text=SPEC_TEXT.replace("status: proposed", "status: banana"))
    with pytest.raises(SpecParseError, match="unknown status"):
        parse_spec(p)


def test_missing_required_key_fails(tmp_path):
    p = _write(tmp_path, text=SPEC_TEXT.replace("spec: SPEC-004\n", ""))
    with pytest.raises(SpecParseError, match="'spec'"):
        parse_spec(p)


def test_monotonic_ids(tmp_path):
    assert SpecCorpus(tmp_path).next_spec_id() == "SPEC-001"
    _write(tmp_path, "SPEC-001-a.md", SPEC_TEXT.replace("SPEC-004", "SPEC-001"))
    _write(tmp_path, "SPEC-002-b.md", SPEC_TEXT.replace("SPEC-004", "SPEC-002"))
    assert SpecCorpus(tmp_path).next_spec_id() == "SPEC-003"


def test_corpus_counts_and_lookup(tmp_path):
    _write(tmp_path, "SPEC-001-a.md", SPEC_TEXT.replace("SPEC-004", "SPEC-001"))
    corpus = SpecCorpus(tmp_path)
    assert corpus.by_id["SPEC-001"].title == "Export monthly usage as CSV"
    assert corpus.counts_by_status()[Status.PROPOSED] == 1


def test_missing_specs_dir_is_empty_corpus(tmp_path):
    corpus = SpecCorpus(tmp_path / "nope")
    assert corpus.docs == [] and corpus.next_spec_id() == "SPEC-001"

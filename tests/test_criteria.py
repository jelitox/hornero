"""Criterion classification tests."""

import pytest

from hornero.criteria import ManualCriterion, ShellCriterion, parse_criteria, parse_criterion

ALLOW = ["pytest", "ruff", "mypy", "python"]


def test_allowlisted_shell():
    c = parse_criterion("pytest tests/export/test_csv.py -q", ALLOW)
    assert isinstance(c, ShellCriterion)
    assert c.head == "pytest" and c.command.startswith("pytest ")


def test_manual_prefix():
    c = parse_criterion("manual: CSV opens correctly in LibreOffice", ALLOW)
    assert isinstance(c, ManualCriterion)
    assert c.description == "CSV opens correctly in LibreOffice"


def test_manual_prefix_case_insensitive():
    assert isinstance(parse_criterion("Manual: check it", ALLOW), ManualCriterion)


def test_unallowlisted_degrades_to_manual():
    c = parse_criterion("rm -rf /", ALLOW)
    assert isinstance(c, ManualCriterion) and c.description == "rm -rf /"


def test_unbalanced_quotes_degrade_to_manual():
    assert isinstance(parse_criterion('pytest "unclosed', ALLOW), ManualCriterion)


def test_empty_raises():
    with pytest.raises(ValueError):
        parse_criterion("   ", ALLOW)


def test_parse_criteria_batch():
    out = parse_criteria(
        ["pytest -q", "manual: looks right", "unknown-tool --flag"], ALLOW
    )
    assert [type(c) for c in out] == [ShellCriterion, ManualCriterion, ManualCriterion]

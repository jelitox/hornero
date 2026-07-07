"""Acceptance-criterion parser (SPEC-001 §5).

Mirrors the dev_loop parser behavior: allowlisted shell heads become
:class:`ShellCriterion`; everything else — ``manual:`` prefix, unallowlisted
heads, unparseable strings — degrades to :class:`ManualCriterion`. The
conservative default matters: misclassifying manual as shell would hand an
arbitrary command to the QA gate. Parsing only; nothing here executes.
"""

import shlex
from collections.abc import Sequence
from dataclasses import dataclass

_MANUAL_PREFIX = "manual:"


@dataclass(frozen=True)
class ShellCriterion:
    command: str
    head: str


@dataclass(frozen=True)
class ManualCriterion:
    description: str


Criterion = ShellCriterion | ManualCriterion


def parse_criterion(raw: str, allowlist: Sequence[str]) -> Criterion:
    text = raw.strip()
    if not text:
        raise ValueError("criterion must be non-empty")
    if text.lower().startswith(_MANUAL_PREFIX):
        return ManualCriterion(text[len(_MANUAL_PREFIX) :].strip())
    try:
        tokens = shlex.split(text)
    except ValueError:  # unbalanced quotes etc. — never executable by accident
        return ManualCriterion(text)
    if tokens and tokens[0] in allowlist:
        return ShellCriterion(command=text, head=tokens[0])
    return ManualCriterion(text)


def parse_criteria(raws: Sequence[str], allowlist: Sequence[str]) -> list[Criterion]:
    return [parse_criterion(raw, allowlist) for raw in raws]

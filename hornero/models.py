"""Core model: RequirementDelta with mechanical evidence verification (SPEC-001 §6).

Hard invariants are validated in code and raise on violation — never silently
fixed. The verbatim check is a literal substring test: no fuzzy matching, no
normalization. A delta whose evidence does not appear verbatim in its source
signal dies upstream (dropped and ledger-logged, CLAUDE.md invariant 1).
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

MAX_EXCERPT_LEN = 500


class DeltaKind(StrEnum):
    """What a signal implies about the spec corpus.

    DUPLICATE deltas are persisted to the ledger for audit but are never
    presented for approval and never produce specs or briefs.
    """

    NEW = "new"  # no existing spec covers this
    CHANGED = "changed"  # modifies scope/criteria of existing spec(s)
    OBSOLETE = "obsolete"  # signal invalidates existing spec(s)
    DUPLICATE = "duplicate"  # already covered; recorded, never dispatched


@dataclass(frozen=True)
class Evidence:
    """Verbatim grounding for a delta. At least one is mandatory."""

    signal_id: str  # e.g. "sig-20260706-a1" (file in .hornero/processed/)
    excerpt: str  # verbatim quote from the signal, <= 500 chars
    locator: str  # "L42-L47" | "00:14:32" | "p.3"

    def __post_init__(self) -> None:
        if not self.signal_id:
            raise ValueError("Evidence.signal_id must be non-empty")
        if not self.excerpt:
            raise ValueError("Evidence.excerpt must be non-empty")
        if len(self.excerpt) > MAX_EXCERPT_LEN:
            raise ValueError(
                f"Evidence.excerpt exceeds {MAX_EXCERPT_LEN} chars "
                f"({len(self.excerpt)})"
            )


@dataclass
class RequirementDelta:
    delta_id: str  # "dlt-<run>-<n>"
    kind: DeltaKind
    title: str
    summary: str  # 1-3 sentences, reconciler's own words
    affected_specs: list[str]  # existing SPEC ids; [] iff kind == NEW
    evidence: list[Evidence]  # len >= 1 — enforced, not prompted
    confidence: float  # 0.0..1.0, reconciler self-estimate
    proposed_patch: str  # full new spec body (NEW) or unified
    # diff against affected spec (CHANGED)
    status: str = "proposed"  # proposed|approved|rejected
    verdicts: list[dict] = field(default_factory=list)  # arena votes, if enabled

    def __post_init__(self) -> None:
        if not self.evidence:
            raise ValueError(f"{self.delta_id}: evidence must be non-empty")
        if (self.kind is DeltaKind.NEW) != (self.affected_specs == []):
            raise ValueError(
                f"{self.delta_id}: kind == NEW iff affected_specs == [] "
                f"(kind={self.kind}, affected_specs={self.affected_specs})"
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"{self.delta_id}: confidence must be in [0.0, 1.0] "
                f"(got {self.confidence})"
            )


def verify_evidence(
    delta: RequirementDelta, signal_text_by_id: Mapping[str, str]
) -> list[Evidence]:
    """Return the evidence items that are NOT verbatim substrings of their
    referenced signal's text. Empty list means fully grounded.

    A reference to an unknown signal_id counts as a mismatch. The check is a
    literal ``in`` — detection only; the caller drops and ledger-logs.
    """
    mismatches: list[Evidence] = []
    for ev in delta.evidence:
        text = signal_text_by_id.get(ev.signal_id)
        if text is None or ev.excerpt not in text:
            mismatches.append(ev)
    return mismatches

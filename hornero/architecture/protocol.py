"""Versioned ArchitectureContext/ArchitectureResult protocol."""

from __future__ import annotations

from typing import Any

from hornero.architecture.model import (
    CONTEXT_SCHEMA,
    RESULT_SCHEMA,
    ArchitectureError,
    canonical_hash,
)


def seal_context(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with a hash covering the entire neutral context."""
    result = dict(payload)
    result["schema"] = CONTEXT_SCHEMA
    result.pop("context_hash", None)
    result["context_hash"] = canonical_hash(result)
    return result


def verify_context(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ArchitectureError("architecture context must be an object")
    if payload.get("schema") != CONTEXT_SCHEMA:
        raise ArchitectureError("unsupported architecture context schema")
    expected = payload.get("context_hash")
    unhashed = dict(payload)
    unhashed.pop("context_hash", None)
    if not isinstance(expected, str) or expected != canonical_hash(unhashed):
        raise ArchitectureError("architecture context hash mismatch")
    return payload


def validate_result(
    payload: object, *, expected_context_hash: str
) -> dict[str, Any]:
    """Reject malformed, stale, or authority-escalating provider results."""
    if not isinstance(payload, dict):
        raise ArchitectureError("architecture result must be an object")
    if payload.get("schema") != RESULT_SCHEMA:
        raise ArchitectureError("unsupported architecture result schema")
    if payload.get("context_hash") != expected_context_hash:
        raise ArchitectureError("architecture result uses stale context")
    allowed = {
        "schema", "context_hash", "reused", "extended", "introduced",
        "deviations", "evidence", "unknowns",
    }
    unknown = set(payload) - allowed
    if unknown:
        raise ArchitectureError(
            f"architecture result has unknown fields: {sorted(unknown)}"
        )
    for field in (
        "reused", "extended", "introduced", "deviations", "evidence", "unknowns"
    ):
        if not isinstance(payload.get(field), list):
            raise ArchitectureError(f"architecture result {field} must be a list")
    return payload

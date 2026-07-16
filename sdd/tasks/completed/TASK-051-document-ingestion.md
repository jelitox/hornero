# TASK-051: Normalize project documents
**Feature**: SPEC-005 | **Status**: done | **Priority**: medium | **Depends-on**: TASK-036, TASK-037

## Scope
Add safe import/normalization for text, Markdown, VTT, HTML, JSON, YAML, PDF, and DOCX with feature-detected extractors and provenance sidecars.
## Acceptance Criteria
- [x] Supported fixtures normalize deterministically with provenance
- [x] Unsupported/encrypted/oversized inputs fail safely

## Completion Note
Added bounded, redacted normalization plus source sidecars for text, Markdown,
VTT, HTML, JSON, YAML, DOCX and feature-detected PDF.

# TASK-020: Toolkit manifest reader + built-in fallback patterns

**Feature**: SPEC-002 — SDD toolkit: install, memory bootstrap, and cross-repo sync
**Spec**: `sdd/specs/SPEC-002-sdd-toolkit-sync.md`
**Status**: pending
**Priority**: high
**Estimated effort**: S (< 2h)
**Depends-on**: none
**Assigned-to**: unassigned

---

## Context

SPEC-002 §4: the upstream repo defines the managed set via
`sdd-toolkit.manifest.json`; when absent (bootstrap period) Hornero falls
back to built-in path patterns matching §1.1 **and warns** (R6). Phase F2.5.

## Scope

- `hornero/sdd_toolkit/__init__.py` + `hornero/sdd_toolkit/manifest.py`:
  - `Manifest` dataclass: `name`, `version`, `managed: list[str]`,
    `scaffold: list[str]`.
  - `FALLBACK_MANIFEST` constant encoding §1.1/§4 patterns verbatim.
  - `load_manifest(upstream_root: Path) -> tuple[Manifest, bool]` — second
    element True when the fallback was used (caller warns). Malformed JSON
    or missing keys ⇒ raise `ManifestError` (fail-closed, never guess).
  - `resolve_managed(upstream_root, manifest) -> list[str]` — expand the
    glob patterns (incl. `**`) against the upstream tree; sorted relative
    POSIX paths; missing matches are fine (empty).
- Tests `tests/test_sdd_manifest.py`.

**NOT in scope**: fetching upstream (TASK-021), copying files (TASK-023).

## Codebase Contract (Anti-Hallucination)

```python
# stdlib only: json, dataclasses, pathlib (Path.glob supports **)
# hornero/sdd_toolkit/ does NOT exist yet — this task creates the package.
# There is no real ai-parrot manifest to read (verified 2026-07-07):
# ai-parrot has no sdd-toolkit.manifest.json — the fallback path is the
# primary tested path, exactly like knowledge/dispatch feature detection.
```

### Does NOT Exist
- ~~`jsonschema`~~ — not installed; validate by hand
- ~~network access~~ — `upstream_root` is always a local directory here

## Acceptance Criteria

- [ ] Manifest file parsed; missing/malformed ⇒ `ManifestError`
- [ ] Absent manifest ⇒ fallback returned with `from_fallback=True`
- [ ] `resolve_managed` expands `*` and `**` deterministically (sorted)
- [ ] `pytest tests/test_sdd_manifest.py -q` green; ruff + mypy clean

## Test Specification

```python
def test_load_real_manifest(tmp_path): ...
def test_absent_manifest_falls_back_with_flag(tmp_path): ...
def test_malformed_manifest_raises(tmp_path): ...
def test_resolve_managed_globs_sorted(tmp_path): ...
```

---

## Completion Note

*(Agent fills this in when done)*

**Completed by**:
**Date**:
**Notes**:

**Deviations from spec**: none

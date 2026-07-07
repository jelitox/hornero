# TASK-009: Reconciler drafting — LLM port, `FakeLLM`, evidence-gated delta drafts

**Feature**: SPEC-001 — Hornero: foundational contracts and MVP scope
**Spec**: `sdd/specs/SPEC-001-hornero-foundation.md`
**Status**: done
**Priority**: high
**Estimated effort**: L (4-8h)
**Depends-on**: TASK-002, TASK-004, TASK-008
**Assigned-to**: unassigned

---

## Context

SPEC-001 §9 steps 1–2: per signal, retrieve top-k context, have an LLM draft
`RequirementDelta`s with mandatory evidence, then run the mechanical verbatim
check **immediately** — non-grounded drafts are dropped and ledger-logged
with reason `evidence_mismatch`, never repaired (CLAUDE.md invariant 1).
Tests use a deterministic `FakeLLM` (invariant 6).

Phase: **F2 — Reconciler**.

---

## Scope

- Implement `hornero/reconciler/__init__.py` and `hornero/reconciler/draft.py`:
  - `LLMPort(Protocol)`: `complete(system: str, user: str) -> str` — the only
    seam to a model. Core never imports a provider SDK.
  - `FakeLLM` **shipped in `hornero/reconciler/testing.py`** (importable by
    tests AND by future fixtures): returns canned JSON responses keyed by a
    match on the user prompt; raises on an unexpected prompt (loud, not
    lenient).
  - `draft_deltas(signal: Signal, signal_text: str, corpus: SpecCorpus, knowledge: KnowledgeLayer, llm: LLMPort, ledger: Ledger, run_id: str) -> list[RequirementDelta]`:
    1. `knowledge.retrieve(...)` for context (top-k specs/decisions).
    2. Prompt the LLM for candidate deltas as JSON (define a strict schema in
       the prompt: kind, title, summary, affected_specs, evidence
       [signal_id, excerpt, locator], confidence, proposed_patch).
    3. Parse defensively: malformed JSON or schema violations ⇒ that draft is
       dropped + ledger-logged (`reason="parse_error"`), not raised to the user.
    4. Construct `RequirementDelta` (model invariants raise → catch per-draft,
       drop + log `invariant_violation`).
    5. Run `verify_evidence(delta, {signal_id: signal_text})`; any mismatch ⇒
       drop delta + `ledger.record_dropped_draft(reason="evidence_mismatch", ...)`.
    6. Return surviving deltas; `delta_id` = `dlt-<run_id>-<n>` (§6).
  - Prompt templates as module constants (plain strings, no template engine).
- Tests in `tests/test_draft.py` with `FakeLLM` covering: grounded draft
  survives; fabricated excerpt dropped + logged; malformed JSON dropped +
  logged; DUPLICATE drafts returned (their filtering-from-HITL is TASK-010/012).

**NOT in scope**: HITL gate (TASK-010), applying deltas (TASK-011), arena
votes (§9 step 3, post-MVP — do not scaffold it), any real LLM client.

---

## Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `hornero/reconciler/__init__.py` | CREATE | package marker |
| `hornero/reconciler/draft.py` | CREATE | LLMPort, draft_deltas, prompts |
| `hornero/reconciler/testing.py` | CREATE | FakeLLM (first-class test double) |
| `tests/test_draft.py` | CREATE | drafting + drop-path tests |

---

## Codebase Contract (Anti-Hallucination)

> **CRITICAL**: verified against the repo on 2026-07-06. Re-verify dependency
> tasks' real signatures on pickup — they are written by other agents.

### Verified Imports
```python
import json                                        # stdlib
from hornero.models import DeltaKind, Evidence, RequirementDelta, verify_evidence  # TASK-002
from hornero.memory.ledger import Ledger           # TASK-004 (record_dropped_draft)
from hornero.memory.knowledge import KnowledgeLayer  # TASK-008
from hornero.ports import Signal                   # TASK-001
from hornero.lifecycle import SpecCorpus           # TASK-003
```

### Existing Signatures to Use
```python
# hornero/models.py (TASK-002):
def verify_evidence(delta, signal_text_by_id) -> list[Evidence]: ...
#   returns NON-GROUNDED evidence items; empty list == fully grounded

# hornero/memory/ledger.py (TASK-004):
#   record_dropped_draft(run_id=..., reason=..., payload=...) — reasons used
#   here: "evidence_mismatch", "parse_error", "invariant_violation"
```

### Does NOT Exist
- ~~`anthropic`, `openai`, `litellm`, `parrot` LLM clients~~ — NOT installed;
  the ONLY model access is `LLMPort`; no provider SDK import anywhere
- ~~`hornero.reconciler` before this task~~ — you create the package
- ~~arena / `RequirementProfile` / `multicoders.arena`~~ — post-MVP (§9 step 3);
  do not scaffold
- ~~retry/repair loops for bad drafts~~ — forbidden: drop + log, never "fix"

---

## Implementation Notes

### Key Constraints
- **Never repair a draft.** A single wrong character in an excerpt kills that
  delta (literal substring check from TASK-002). This is the product's core
  trust property (R1).
- One LLM call per signal (MVP); the JSON response may contain 0..n drafts.
- All drop paths MUST write to the ledger — silent drops are bugs.
- `FakeLLM` lives in shipped code (`reconciler/testing.py`), mirroring the
  real-engine/simulated-externals pattern, so e2e fixtures (TASK-012) and
  downstream repos can reuse it.
- Determinism: given the same FakeLLM script + fixture text, output deltas
  (ids included) are identical across runs.

### References in Codebase
- SPEC-001 §6 (delta/evidence contract, `dlt-<run>-<n>`), §9 steps 1–2,
  §13 R1; CLAUDE.md invariants 1 and 6.

---

## Acceptance Criteria

- [ ] Grounded FakeLLM draft → one `RequirementDelta` returned with verified evidence
- [ ] Fabricated excerpt → delta absent from result AND `dropped_drafts` row with `reason="evidence_mismatch"`
- [ ] Malformed JSON → empty result + `parse_error` row; no exception escapes
- [ ] `kind=NEW` with `affected_specs` populated → dropped + `invariant_violation` row
- [ ] `delta_id` format `dlt-<run>-<n>`, deterministic
- [ ] All tests pass: `pytest tests/test_draft.py -q`; `ruff check` + `mypy hornero` clean

---

## Test Specification

```python
# tests/test_draft.py
from hornero.reconciler.draft import draft_deltas
from hornero.reconciler.testing import FakeLLM


def test_grounded_draft_survives(tmp_path): ...
def test_fabricated_excerpt_dropped_and_logged(tmp_path): ...
def test_malformed_json_dropped_and_logged(tmp_path): ...
def test_invariant_violation_dropped_and_logged(tmp_path): ...
def test_delta_ids_deterministic(tmp_path): ...
```

---

## Agent Instructions

When you pick up this task:

1. **Read the spec** at the path listed above for full context
2. **Check dependencies** — verify TASK-002, TASK-004, TASK-008 are in `sdd/tasks/completed/`
3. **Verify the Codebase Contract** — before writing ANY code
4. **Update status** in `sdd/tasks/index/hornero-foundation.json` → `"in-progress"`
5. **Implement** following the scope, codebase contract, and notes above
6. **Verify** all acceptance criteria are met
7. **Move this file** to `sdd/tasks/completed/TASK-009-reconciler-drafting.md`
8. **Update index** → `"done"`
9. **Fill in the Completion Note** below

---

## Completion Note

**Completed by**: claude-fable-5 (session 0d52d2f9)
**Date**: 2026-07-06
**Notes**: hornero/reconciler/draft.py (LLMPort protocol, strict-JSON prompt, per-item defensive parse, verify_evidence gating, all drop paths ledger-logged with evidence_mismatch/parse_error/invariant_violation) + testing.py (FakeLLM, loud on unexpected prompts, from_file for fake:<script> configs). 7 tests green.

**Deviations from spec**: none

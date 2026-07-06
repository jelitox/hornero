---
spec: SPEC-001
title: Hornero — foundational contracts and MVP scope
status: approved
kind: new_feature
created: 2026-07-06
owner: javier@javierleon.dev
depends_on: []
supersedes: []
---

# SPEC-001 — Hornero: foundational contracts and MVP scope

> **Name:** `hornero` — the South American ovenbird that builds its own house,
> methodically, layer by layer. Fits the ai-parrot bird ecosystem. Cleared
> 2026-07-06: PyPI name free; only unregistered hobby projects share the name
> on GitHub; no trademark conflicts.

## 1. Context

Hornero is an open-source, repo-native **product loop** agent. Given a repository,
it continuously:

1. Ingests requirement signals (meeting notes, transcripts, documents).
2. Reconciles them against the current spec state and proposes typed deltas.
3. After human approval, dispatches build work to coding agents.
4. Writes code, updated specs, ADRs, and regenerated HTML reports back into
   the **same repo**, in the **same PR**.
5. Reindexes its knowledge base on merge, so the next signal is reconciled
   against the built state, not the original intent.

It is a thin layer over existing components:

| Concern | Provided by | Hornero adds |
|---|---|---|
| Flow engine | `ai-parrot` (`AgentsFlow`) | flow wiring only |
| Knowledge | `ai-parrot` (`PageIndex`, `GraphIndex`) | feature-detected, fallback included |
| Agent backends | `multicoders.backends` (`CliBackend`, `ApiBackend`, `MockBackend`) | nothing — consumed as a dependency |
| Consensus validation | `multicoders.arena` + `DomainProfile` | a `RequirementProfile` (optional, post-MVP) |
| Requirement reconciliation | — | **the reconciler (new)** |
| Spec lifecycle | — | **repo-native spec state machine (new)** |
| Reports | — | **HTML generators over the knowledge layer (new)** |

Personal pet project, external to T-ROC. Corporate adapters (Fireflies, Jira,
CloudWatch) are **out of scope**; only the ports they would implement are in
scope.

## 2. Goals

- G1. A repo-native loop that works end-to-end with **zero external
  services**: filesystem inbox, markdown specs as tracker, `MockBackend` or
  `CliBackend` (BYO-auth) as dispatcher.
- G2. Three stable ports (`SignalSource`, `TrackerPort`, `DispatchPort`) so
  any environment can plug its own adapters without touching core.
- G3. Every proposed requirement change carries **verbatim evidence** and
  passes a **fail-closed HITL gate** before anything is created or dispatched.
- G4. The repo is the single source of truth: specs, decisions, reports, and
  knowledge indexes are files under version control.
- G5. Out-of-the-box HTML reports (capabilities map, workflow map, demo flows)
  generated from the knowledge layer, never from parametric memory.

## 3. Non-goals

- NG1. No Fireflies / Jira / Slack / CloudWatch adapters in this repo.
- NG2. No token proxying or pooling — inherits Multicoders' hard constraint:
  `CliBackend` runs in the user's own authenticated session, strips provider
  API-key env vars, and is never an automatic fallback for `ApiBackend`.
- NG3. No autonomous dispatch. `hornero build` without an approved spec is a no-op.
- NG4. No web UI in MVP. Terminal HITL first; the dev_loop-style
  server + WebSocket UI is a later phase.
- NG5. Not a replacement for Multicoders or ai-parrot; Hornero composes them.

## 4. Repo layout (contract)

```
<product-repo>/
├── .hornero/
│   ├── inbox/                  # SignalSource default: drop .md/.txt/.vtt here
│   ├── processed/              # acked signals, moved after reconciliation
│   ├── knowledge/              # PageIndex trees + graph store (committed)
│   ├── ledger.db               # SQLite: runs, deltas, verdicts, checkpoints
│   └── config.yaml             # ports, backend order, criterion allowlist, models
├── product/
│   ├── specs/                  # SPEC-NNN-slug.md — requirement units w/ frontmatter
│   ├── decisions/              # ADR-NNN-slug.md — written by reconciler + dev-loop
│   └── reports/                # generated HTML (capabilities, workflows, demo flows)
└── src/                        # whatever the dev-loop builds
```

Rules:

- `.hornero/knowledge/` is **committed** (repo is self-contained and clonable
  with memory included); `hornero reindex` rebuilds it deterministically from
  `product/` + `.hornero/processed/`.
- `ledger.db` is gitignored; it is operational state, not knowledge.
- Spec IDs are monotonic per repo (`SPEC-001`, `SPEC-002`, …); ADRs likewise.

## 5. Spec lifecycle (state machine)

Specs are markdown files with YAML frontmatter. `status` is the state:

```
proposed ──approve──▶ approved ──build──▶ building ──PR opened──▶ review
   │                                          │                     │
 reject                                    build fails            merge
   ▼                                          ▼                     ▼
rejected                                needs_human               done
```

Additional terminal state: `obsolete` (set by an approved `OBSOLETE` delta).

Frontmatter contract:

```yaml
---
spec: SPEC-004
title: Export monthly usage as CSV
status: approved            # proposed|approved|building|review|done|rejected|needs_human|obsolete
kind: new_feature           # bug|enhancement|new_feature
created: 2026-07-06
sources: [sig-20260706-a1]  # signal ids that produced/changed this spec
supersedes: []
acceptance_criteria:
  - "pytest tests/export/test_csv.py -q"        # ShellCriterion (allowlisted head)
  - "manual: CSV opens correctly in LibreOffice" # ManualCriterion (prefix `manual:`)
---
```

The criterion syntax intentionally mirrors the dev_loop parser (allowlisted
shell heads → `ShellCriterion`; everything else / `manual:` prefix →
`ManualCriterion`) so specs translate 1:1 into briefs.

## 6. Core model — `RequirementDelta`

```python
from dataclasses import dataclass, field
from enum import StrEnum


class DeltaKind(StrEnum):
    NEW = "new"            # no existing spec covers this
    CHANGED = "changed"    # modifies scope/criteria of existing spec(s)
    OBSOLETE = "obsolete"  # signal invalidates existing spec(s)
    DUPLICATE = "duplicate"  # already covered; recorded, never dispatched


@dataclass(frozen=True)
class Evidence:
    """Verbatim grounding for a delta. At least one is mandatory."""
    signal_id: str      # e.g. "sig-20260706-a1" (file in .hornero/processed/)
    excerpt: str        # verbatim quote from the signal, <= 500 chars
    locator: str        # "L42-L47" | "00:14:32" | "p.3"


@dataclass
class RequirementDelta:
    delta_id: str                       # "dlt-<run>-<n>"
    kind: DeltaKind
    title: str
    summary: str                        # 1-3 sentences, reconciler's own words
    affected_specs: list[str]           # existing SPEC ids; [] iff kind == NEW
    evidence: list[Evidence]            # len >= 1 — enforced, not prompted
    confidence: float                   # 0.0..1.0, reconciler self-estimate
    proposed_patch: str                 # full new spec body (NEW) or unified
                                        # diff against affected spec (CHANGED)
    status: str = "proposed"            # proposed|approved|rejected
    verdicts: list[dict] = field(default_factory=list)  # arena votes, if enabled
```

Hard invariants (validated in code, raise on violation — never silently fixed):

- `evidence` non-empty; each `excerpt` must be a verbatim substring of the
  referenced signal (checked mechanically at delta creation).
- `kind == NEW` ⇔ `affected_specs == []`.
- `DUPLICATE` deltas are persisted to the ledger for audit but are not
  presented for approval and never produce specs or briefs.
- No delta mutates `product/specs/` before `status == "approved"`.

## 7. Ports

All three are `typing.Protocol`s in `hornero/ports.py`. Core never imports an
adapter; adapters are resolved from `config.yaml` (same explicit-order +
capability + health pattern as `multicoders.backends.resolver`).

```python
class Signal(TypedDict):
    signal_id: str
    kind: str            # "meeting_notes" | "transcript" | "document" | "idea"
    path: str            # local path after normalization
    received_at: float


class SignalSource(Protocol):
    def poll(self) -> list[Signal]: ...
    def ack(self, signal_id: str) -> None: ...   # move to processed/, idempotent


class TrackerPort(Protocol):
    def upsert(self, spec_path: str) -> str: ...          # returns external ref
    def transition(self, ref: str, status: str) -> None: ...
    def comment(self, ref: str, body: str) -> None: ...


class BuildBrief(TypedDict):
    spec_id: str
    kind: str                    # bug|enhancement|new_feature
    summary: str
    description: str             # rendered from spec body + linked ADRs
    acceptance_criteria: list[str]
    repo_path: str


class BuildResult(TypedDict):
    status: str                  # completed|failed|needs_human
    pr_url: str | None
    branch: str | None
    log_path: str


class DispatchPort(Protocol):
    def dispatch(self, brief: BuildBrief) -> BuildResult: ...
```

MVP adapters (the only ones in this repo):

| Port | MVP adapter | Notes |
|---|---|---|
| `SignalSource` | `InboxSource` | polls `.hornero/inbox/`, acks by moving to `processed/` |
| `TrackerPort` | `RepoTracker` | the spec file IS the ticket; `transition` edits frontmatter; `comment` appends to a `## Log` section |
| `TrackerPort` | `GitHubIssuesTracker` (optional) | thin `gh` wrapper, feature-flagged |
| `DispatchPort` | `MulticodersDispatch` | wraps `multicoders.backends` (`--backend {cli,mock}`); `mock` is the test default |

## 8. Knowledge layer

Mirror Multicoders Fase 4 exactly — feature-detect, degrade gracefully:

- **documents** — `PageIndexDocumentMemory` over `product/` +
  `.hornero/processed/` when `parrot.knowledge.pageindex` is importable
  (note FEAT-198 path: `parrot.knowledge.pageindex`, not `parrot.pageindex`).
- **graph** — `GraphIndexEpisodicMemory` for entities/relations
  (spec ↔ signal ↔ decision ↔ component) when available.
- **fallback** — token-overlap retrieval (à la `JsonDecisionMemory`) so the
  reconciler works on any ai-parrot pin. `available()` gates the upgrade;
  no code path may hard-require the indexes.

`hornero reindex` is the only writer of `.hornero/knowledge/`; it is deterministic
given the repo state plus the configured summary model (model + prompt hashes
are recorded in the index manifest for reproducibility).

## 9. The reconciler

A single node (later: an `AgentsFlow` node) with this contract:

```
reconcile(signals: list[Signal], spec_state: SpecCorpus) -> list[RequirementDelta]
```

Pipeline per signal:

1. **Retrieve** — top-k relevant specs/decisions from the knowledge layer.
2. **Draft deltas** — LLM proposes deltas with mandatory evidence; the
   verbatim-substring check runs immediately and drops non-grounded deltas
   (dropped drafts are logged to the ledger with reason `evidence_mismatch`).
3. **(Post-MVP) Arena vote** — a `RequirementProfile` domain: N judges vote
   "does this signal genuinely imply this delta?"; majority approval required
   before the delta reaches the human.
4. **HITL gate** — terminal prompt (rich diff view): approve / reject / edit
   per delta. Fail-closed: no TTY, no approval, no effect — identical
   philosophy to Oddie's `ConfirmationGuard` with `human_manager=None`.
5. **Apply** — approved deltas write/patch spec files, append an ADR when the
   delta reverses a prior decision, and `ack()` the signal.

## 10. CLI surface (MVP)

```
hornero init                      # scaffold .hornero/ + product/ in an existing repo
hornero status                    # spec counts by state, pending inbox, index health
hornero reconcile [--dry-run]     # poll → deltas → HITL → apply
hornero build [SPEC-ID ...]       # approved specs → briefs → DispatchPort
hornero reindex                   # rebuild .hornero/knowledge/ from repo state
hornero report [--only <name>]    # regenerate product/reports/*.html
```

`--dry-run` on `reconcile` prints deltas without the HITL gate and applies
nothing. `build` with `backend: mock` produces a deterministic fake PR — this
is the e2e test path (same philosophy as `e2e_demo.py`: real engine, simulated
externals).

## 11. Reports

Generators read **only** the knowledge layer + spec frontmatter (never
parametric memory) and render self-contained static HTML (no build step) to
`product/reports/`:

- `capabilities.html` — what the product does today, grouped by component,
  each capability linked to its spec + originating signals.
- `workflows.html` — flows extracted from the graph (spec → components →
  decisions), business and technical views.
- `traceability.html` — signal → delta → spec → PR → merge chain per
  requirement (the audit view; falls out of the ledger for free).

Regeneration triggers: `hornero report` manually, and as the final step of a
successful `build` so the PR ships code + spec + refreshed reports atomically.

## 12. Phases

| Phase | Deliverable | Gate (deterministic) |
|---|---|---|
| **F1 — Skeleton** | `hornero init/status`, spec state machine, `InboxSource`, `RepoTracker`, ledger schema | `pytest tests/test_lifecycle.py tests/test_inbox.py -q` green; `hornero init && hornero status` exit 0 on empty repo |
| **F2 — Reconciler** | delta model + evidence check + HITL terminal + `reconcile` | fixture inbox (3 notes) yields expected delta set with `FakeLLM`; every delta evidence-verified; `--dry-run` mutates nothing (git diff empty) |
| **F3 — Dispatch bridge** | `MulticodersDispatch`, spec→brief translation, criterion parser | e2e: approved fixture spec → `mock` backend → spec transitions `approved→building→review`; fake PR URL recorded |
| **F4 — Write-back** | ADR writer, spec patch in PR branch, merge→`reindex` hook (git hook or CI step) | post-"merge" fixture: reindex picks up new spec; re-running `reconcile` on the same signal yields `DUPLICATE` |
| **F5 — Reports** | three HTML generators + templates | generators run offline on fixture repo; output contains every `done` spec; zero network calls (asserted) |

Each phase is independently useful (F1+F2 already give a curated,
evidence-grounded spec base even if you never dispatch anything).

## 13. Risks and mitigations

- **R1. Requirement hallucination from ambiguous signals.** Mitigation:
  mechanical verbatim-evidence check (drops, not warns) + HITL fail-closed +
  optional arena vote. Confidence is displayed to the human, never used to
  auto-approve.
- **R2. Spec/code drift.** Mitigation: acceptance criteria live in the spec
  and become the dev-loop QA gate verbatim; `done` requires the criteria that
  the spec itself declares.
- **R3. Stale knowledge.** Mitigation: merge-triggered `reindex`; `hornero
  status` surfaces index-vs-HEAD staleness.
- **R4. ai-parrot pin lacks knowledge modules.** Mitigation: token-overlap
  fallback is a first-class citizen with its own tests, not a stub.
- **R5. Scope creep toward FieldSync Manager.** Mitigation: NG1 — corporate
  adapters live outside this repo, full stop.

## 14. Open questions

- OQ1. Delta `edit` in the HITL gate: inline editor (`$EDITOR` on the patch)
  vs. reject-and-rerun? Leaning `$EDITOR` — cheap and familiar.
- OQ2. Should `DUPLICATE` deltas optionally `comment()` on the covering spec
  ("mentioned again in sig-X") as signal-strength telemetry? Leaning yes, F4.
- OQ3. Multi-product: one Hornero per repo (current design) vs. a workspace mode?
  Deferred — per-repo keeps the mental model trivial.
- OQ4. ~~Name~~ **Resolved 2026-07-06:** `hornero` (Loom discarded — registered
  trademark of a funded software company; `telar` kept as fallback).
- OQ5. `multicoders` is not pinned in `pyproject.toml` and not installed in the
  dev venv (verified 2026-07-06), yet §7 names `multicoders.backends` as the
  `DispatchPort` MVP adapter. Conservative interpretation taken for TASK-014:
  ship a built-in deterministic `MockBackend` as the first-class default and
  feature-detect `multicoders.backends` (same pattern as §8 uses for parrot);
  absent backends yield `needs_human`, never a substitute. Pinning multicoders
  (and how) remains open.

## Log

- 2026-07-06 — Spec drafted (status: proposed).
- 2026-07-06 — Decomposed into 19 tasks (`sdd/tasks/index/hornero-foundation.json`)
  while still `status: proposed` — flagged during `/sdd-task`; approve the spec
  before starting implementation. OQ5 added (multicoders not pinned; TASK-014
  takes the feature-detect + MockBackend interpretation).
- 2026-07-06 — Approved by owner (via "continúa, prueba el spec-001"); implementation
  of F1 begins.

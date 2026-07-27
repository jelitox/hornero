---
spec: SPEC-011
title: Independent multi-agent advisory runs through Multicoders
status: review
kind: new_feature
created: 2026-07-26
owner: javier@javierleon.dev
depends_on: [SPEC-004, SPEC-005, SPEC-009, SPEC-010]
supersedes: []
sources:
  - owner-directive-20260726-independent-multi-agent-advisory
  - multicoders-runtime-audit-20260726
acceptance_criteria:
  - "pytest -q"
  - "ruff check ."
  - "mypy hornero"
  - "python scripts/changelog.py validate"
---

# SPEC-011 - Independent multi-agent advisory runs through Multicoders

## 1. Context

Hornero already creates grounded build briefs, records agent runs and exposes a
provenance-rich knowledge graph. Multicoders already knows how to invoke Codex,
Claude Code and Gemini CLI. The missing capability is a governed advisory
workflow in which multiple providers receive the same neutral problem
statement, work independently, and are compared only after their individual
answers are complete.

This workflow is intended for adversarial code review, design opinions,
brainstorming and research cross-checks. It is not a second implementation
path. Its value depends on preserving epistemic independence: a provider must
not see another provider's answer or the coordinator's preferred conclusion
before producing its own first-pass opinion.

The implementation boundary is:

- **Hornero owns** requirement/spec/ADR grounding, bounded context packs,
  policy, budgets, evidence, run records, dispositions and graph projection.
- **Multicoders owns** provider discovery, process execution, parallel fan-out,
  provider sessions, normalized responses and optional transport delivery.
- **Provider CLIs own** their authentication and native capabilities. API
  providers are explicit opt-in only and never an automatic fallback.

## 2. Goals and non-goals

### Goals

1. Ask two or more distinct providers for independent perspectives using the
   same neutral brief.
2. Support `review`, `brainstorm`, `research` and `design-opinion` advisory
   modes without granting implementation authority.
3. Preserve every provider answer and force an explicit disposition for each
   actionable finding: `CONFIRM`, `REJECT` with reason, or `ESCALATE`.
4. Continue safely when a provider times out or is unavailable, subject to a
   declared minimum quorum.
5. Make the full advisory lineage queryable from Hornero's development graph.

### Non-goals

- Automatically editing code, opening a PR, merging or deploying based only on
  advisory output.
- Treating consensus as proof or silently choosing the majority answer.
- Sharing hidden chain-of-thought or asking providers to expose it.
- Replacing native provider authentication with a Hornero-managed credential.
- Routing to a billed API because a subscription-backed CLI is unavailable.

## 3. User-facing contract

The Hornero surface is:

```text
hornero consult review [--uncommitted | --base REF | --commit SHA]
                       [--providers codex,claude,gemini]
                       [--quorum N] [--autonomous] [--json]
hornero consult brainstorm --spec SPEC-NNN --question TEXT [...]
hornero consult research --spec SPEC-NNN --question TEXT [...]
hornero consult design-opinion --spec SPEC-NNN --question TEXT [...]
hornero consult show RUN_ID [--json]
hornero consult resume RUN_ID --provider NAME --question TEXT
```

`hornero consult` creates a governed advisory request and delegates execution
to a versioned Multicoders command/API contract. A direct Multicoders command
may expose the same runtime for other callers, but Hornero remains the source
of approved product context and the audit record for Hornero projects.

The command defaults to read-only execution. `--autonomous` means unattended
collection, validation and recording within configured limits; it does not
grant write, merge, deployment or spending authority.

## 4. Neutral brief and context grounding

### 4.1 Required brief fields

Every first-pass provider receives byte-equivalent logical content:

```json
{
  "mode": "review|brainstorm|research|design-opinion",
  "requirement": "verbatim user request or approved requirement",
  "question": "the neutral question to answer",
  "evidence": [{"locator": "...", "sha256": "...", "content": "..."}],
  "constraints": [{"source": "SPEC/ADR locator", "quote": "verbatim text"}],
  "review_target": {"kind": "uncommitted|base|commit|context", "value": "..."},
  "requested_output": "findings, evidence, risks, unknowns, recommendation"
}
```

Hornero builds the evidence set from the approved spec, linked decisions,
bounded semantic context and the selected diff/commit. Each item carries a
stable locator and content hash.

### 4.2 Independence invariant

Before all phase-one responses close, the brief MUST NOT contain:

- the coordinator's reasoning, justification, preferred solution or
  confidence;
- another provider's answer, summary, score or provider identity;
- leading instructions that ask the provider to ratify a proposed conclusion.

The requirement, diff/context and question are allowed. Approved decisions are
hard constraints and are quoted verbatim. The system records a normalized
`brief_hash`; all phase-one runs in the same advisory run must reference that
hash.

## 5. Two-phase execution

### Phase A - independent fan-out

1. Resolve enabled providers and capabilities without starting a process.
2. Apply per-provider authentication, health, quota and cooldown checks.
3. Spawn eligible providers concurrently with isolated child environments.
4. Capture stdout, stderr, exit state, duration, native session identifier and
   normalized findings independently.
5. Close or time out every slot before exposing phase-one output to any
   synthesizer.

For native Codex review, Multicoders uses the provider's supported selector:
uncommitted changes, a base ref, or a commit. Brainstorm and research use
read-only sandboxing and a scratch output file where the CLI separates progress
noise from the final answer.

### Phase B - comparison and synthesis

Only after Phase A closes may a synthesizer see the provider answers. It
produces:

- agreements with the supporting provider IDs;
- disagreements with each position represented;
- unique findings and their evidence;
- unresolved or low-confidence claims;
- a recommended disposition, never an automatic implementation.

A deterministic coordinator may synthesize structurally without an LLM. If an
LLM synthesizer is enabled, its provider, input hashes and output are recorded
as a separate run and cannot overwrite the originals.

## 6. Finding and disposition model

Each normalized finding contains:

```text
finding_id, provider, category, severity, summary, evidence locators,
confidence, recommendation, status
```

The lifecycle is `reported -> confirmed|rejected|escalated`. Every reported
finding must receive one of:

- `CONFIRM`: accepted for planning, with the confirming actor and rationale;
- `REJECT`: retained with a concrete reason and contrary evidence;
- `ESCALATE`: left unresolved for a named human decision or further research.

No finding is deleted because it was outvoted. Deduplication groups equivalent
findings while preserving every provider's original wording and evidence.

## 7. Runtime, authentication and billing safety

1. Provider commands are fixed argv templates; no shell interpolation.
2. The default sandbox is read-only. Advisory mode cannot request a writable
   sandbox or invoke implementation tools.
3. Child environments are created from a copy and filtered per provider.
   Removing an API credential for one invocation must never mutate the parent
   process environment.
4. Subscription-backed CLI authentication is preferred when configured.
   `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` and equivalent
   credentials are not forwarded unless that provider configuration explicitly
   selects an API mode and declares its budget.
5. Missing authentication, a quota error or an unavailable binary produces a
   typed provider outcome. It never triggers a billed fallback.
6. Provider stdout/stderr and prompts pass through Hornero redaction before
   persistence.
7. Concurrency, wall-clock time, attempts, output bytes and optional cost units
   have per-run and per-provider limits.

## 8. Failure, quorum and autonomous-mode policy

An advisory request declares `requested_providers`, `minimum_quorum` and
`required_providers`. Partial results are retained.

- If quorum succeeds, synthesis may proceed and unavailable providers are
  shown explicitly.
- If quorum fails, the run ends `needs_human`; no authoritative synthesis is
  emitted.
- High-risk security, compliance, destructive-operation or permission findings
  always escalate even when all providers agree.
- Autonomous mode may retry a transient failure within the declared attempt and
  time budget. It may not bypass cooldowns, weaken sandboxing, lower quorum,
  add credentials or change providers.
- Cancellation terminates child processes, preserves completed outputs and
  records which slots were cancelled.

## 9. Trace, ledger and development-graph contract

Hornero stores primary runtime artifacts under
`.hornero/runs/<run_id>/advisory/` and records:

- advisory request, neutral brief and source hashes;
- one child run per provider, including provider/model/version, sandbox,
  command fingerprint, session ID, timestamps and outcome;
- raw-redacted and normalized provider outputs;
- synthesis, finding groups and all dispositions;
- budget consumption, retries, quorum decision and errors.

The semantic graph projects:

```text
Requirement --requested--> AdvisoryRun
AdvisoryRun --grounded_by--> Source | Spec | Decision | Diff
AdvisoryRun --has_perspective--> ProviderRun
ProviderRun --reported--> AdvisoryFinding
AdvisoryFinding --supported_by--> Evidence
AdvisoryFinding --disposed_as--> Disposition
AdvisoryRun --summarized_by--> Synthesis
ProviderRun --continues_as--> ProviderRun
```

Every node and relation has source provenance. Reindexing is deterministic and
the graph remains valid when a provider is unavailable or an output is
rejected.

## 10. Implementation phases

| Phase | Deliverable | Deterministic gate |
|---|---|---|
| F25 - contract and isolation | Versioned Hornero/Multicoders request-response schema, neutral brief builder, child-env filter and provider capability discovery | Golden briefs are equivalent across providers; planted coordinator conclusions and credentials are absent; parent environment is unchanged |
| F26 - parallel advisory runtime | Concurrent fan-out, native review selectors, timeout/cancel/cooldown, session capture and minimum quorum | Fake providers prove overlap in execution, stable ordering of persisted results, partial success and fail-closed quorum |
| F27 - synthesis and disposition | Normalization, deduplication, agreement/disagreement synthesis and mandatory triage | Conflicting fixtures preserve both positions; every finding ends confirmed, rejected or escalated |
| F28 - audit and graph | Ledger records, trace artifacts, semantic projection, CLI show/resume and operator documentation | A fixture traverses requirement -> advisory run -> provider run -> finding -> evidence -> disposition with provenance |

## 11. Test specification

- Unit tests use deterministic fake provider processes; no network, real model
  or installed CLI is required.
- A timing-controlled test proves providers begin before any first response is
  exposed to synthesis.
- Prompt fixtures prove phase-one briefs contain no coordinator conclusion or
  peer output and use one `brief_hash`.
- Environment fixtures prove provider-specific key filtering and no mutation of
  `os.environ`.
- Failure fixtures cover missing binary, auth failure, quota/cooldown, timeout,
  malformed output, cancellation, output truncation and quorum failure.
- Graph tests assert every advisory entity/relation has provenance and no
  dangling endpoint.
- Optional local smoke tests are marked and never run in CI by default.

## 12. Open questions

- OQ1. Should the first implementation require two distinct provider families,
  or merely two configured providers? Distinct families provide stronger
  independence but can reduce availability.
- OQ2. Should the default synthesizer be deterministic-only, or a separately
  selected provider excluded from Phase A?
- OQ3. Which Multicoders compatibility boundary will be stable first: a JSON
  CLI protocol, an optional Python dependency, or both over one schema?

## 13. Log

- 2026-07-26 - Owner requested specs and development-graph documentation for
  Codex as an independent second-opinion agent alongside Claude/Multicoders,
  including code review, brainstorming, research and parallel synthesis.
- 2026-07-26 - Repository audit confirmed existing Hornero grounding/audit
  primitives and Multicoders provider subprocesses, while identifying
  sequential context leakage, incomplete Hornero-to-Multicoders dispatch and
  child-environment billing risks as implementation gaps.
- 2026-07-26 - Owner authorized implementation and publication across Hornero
  and Multicoders. F25-F28 implemented with concurrent neutral fan-out,
  child-only credential filtering, JSON protocol, quorum, triage, ledger and
  semantic graph projection; status moved to review pending PR.

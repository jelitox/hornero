---
spec: SPEC-005
title: Autonomous project factory and continuous intelligence loop
status: done
kind: new_feature
created: 2026-07-16
owner: javier@javierleon.dev
depends_on: [SPEC-001, SPEC-002, SPEC-003, SPEC-004]
supersedes: []
sources: [owner-directive-20260716]
acceptance_criteria:
  - "pytest -q"
  - "ruff check ."
  - "mypy hornero"
---

# SPEC-005 - Autonomous project factory and continuous intelligence loop

## 1. Context

Hornero currently reconciles signals into specs, builds a file-oriented local
index, and dispatches approved work. It does not yet create a repository and
full stack from a versioned blueprint, model requirements and controls as a
semantic graph, validate that graph on every invocation, or run a bounded
continuous-improvement loop.

The owner approved the 20-item audit backlog on 2026-07-16 and requested that
the implementation plan and progress remain recoverable across agent sessions.

## 2. Goals

- Harden all existing trust boundaries before autonomous execution.
- Create repositories from composable, versioned blueprints.
- Store a provenance-rich graph connecting sources, requirements, criteria,
  decisions, tasks, code, tests, controls, risks, findings, and runs.
- Validate and repair derived graph state before commands make decisions.
- Ingest common project documents through safe, extensible adapters.
- Integrate real LLM and coding CLI seams without implicit billing.
- Detect architecture, security, compliance, dependency, quality, and test
  improvements and persist them as reviewable findings.
- Execute low-risk approved work through a bounded controller with branch,
  verification, audit, and rollback contracts.

## 3. Safety invariants

1. Existing evidence, HITL, billing, drift, and deterministic-test invariants
   remain in force.
2. Untrusted paths never escape the repository or configured workspace.
3. Secret-bearing content is redacted or excluded before entering retrieval.
4. Every semantic node and edge has provenance and a stable content identity.
5. Graph validation runs before decision-making commands; corrupt derived
   state is rebuilt, while corrupt primary records fail closed.
6. Autonomous execution is disabled by default. Risky, destructive, billed,
   compliance-sensitive, or permission-expanding work always requires HITL.
7. The controller operates with explicit budgets and produces no direct push
   to a protected/default branch.
8. Every applied improvement must pass declared gates or be rolled back in its
   isolated branch/worktree, with the failure retained as knowledge.

## 4. Deliverables

### F12 - Hardening

Path containment, redacted knowledge, prompt trust boundaries, atomic build
state, concurrent run IDs, accurate apply outcomes, strict config validation,
durable queue semantics, repository-root discovery, and index self-healing.

### F13 - Project factory

`hornero new NAME --blueprint NAME` initializes git, renders a versioned and
composable blueprint, writes a lock, validates destinations, and optionally
creates an initial commit. `hornero blueprint list|status` reports inventory
and drift without mutating user files.

### F14 - Semantic knowledge graph

The graph schema gains typed entities and relations, provenance, confidence,
validity, source hashes, and history. Parsers derive entities from specs, task
indexes, decisions, controls, Python symbols/imports, tests, and ingested
documents. Hybrid lexical/graph retrieval remains offline-first.

`hornero validate` reports schema errors, dangling links, stale sources,
contradictions, missing traceability, secret exposure, and coverage gaps. It
returns non-zero on blocking findings and can rebuild derived state safely.

### F15 - Providers and ingestion

Document ingestion normalizes text, Markdown, VTT, HTML, JSON, YAML, PDF and
DOCX through feature-detected extractors. Model adapters support local command
and OpenAI-compatible HTTP providers with explicit configuration, budgets,
timeouts, and redacted audit. Coding dispatch supports a real argv-based CLI
adapter with BYO authentication and no shell interpolation.

### F16 - Continuous improvement

Policy packs inspect architecture, security, compliance, dependencies,
performance, tests, documentation, and graph integrity. Findings have stable
IDs, severity, evidence, remediation, confidence, risk, and lifecycle.

`hornero improve scan|plan|run|status` implements observe -> validate -> find ->
prioritize -> approve -> execute -> verify -> learn. Scan and plan are safe and
unattended. Run requires explicit enablement plus policy approval; medium/high
risk findings stop for HITL. All activity is ledgered and added to the graph.

## 5. Acceptance gates

- **F12:** regression fixtures prove traversal rejection, redaction, strict
  config types, truthful ledger outcomes, root discovery, concurrency-safe IDs,
  and recovery from corrupt derived indexes.
- **F13:** a temporary directory becomes a git repository with a runnable
  selected stack; a second render is idempotent and drift is reported.
- **F14:** a fixture requirement traverses source -> requirement -> criterion ->
  task -> code -> test -> control; invalid edges and stale provenance fail.
- **F15:** deterministic fake HTTP/CLI runners prove provider routing, budgets,
  timeouts, safe argv dispatch, and normalized ingestion without network.
- **F16:** planted architecture/security/compliance/test gaps yield stable
  findings; low-risk fake execution passes gates and records learning; risky
  work remains pending without approval.
- **Release:** `pytest -q`, `ruff check .`, and `mypy hornero` are green.

## 6. Progress authority

The resumable execution checkpoint is
`sdd/state/autonomous-improvement/PROGRESS.md`. It is updated at every task
boundary and is part of the knowledge corpus indexed by `hornero reindex`.

## 7. Log

- 2026-07-16 - Owner approved all 20 audit items and requested autonomous
  implementation with persistent plan/progress memory.
- 2026-07-16 - SPEC-005 approved; TASK-036 through TASK-055 decomposed.
- 2026-07-16 - F12-F16 implemented; 20 audit tasks closed with persistent
  completion records, deterministic regression coverage and operator docs.
- 2026-07-16 - Release gate green: 291 tests, ruff, mypy; project graph fresh
  with zero blocking validation findings.

---
spec: SPEC-006
title: Production intelligence and autonomous operations platform
status: done
kind: new_feature
created: 2026-07-16
owner: javier@javierleon.dev
depends_on: [SPEC-005]
supersedes: []
sources: [owner-directive-20260716-batch-2]
acceptance_criteria:
  - "pytest -q"
  - "ruff check ."
  - "mypy hornero"
---

# SPEC-006 - Production intelligence and autonomous operations platform

## 1. Context

SPEC-005 established a safe project factory, semantic knowledge graph,
providers, policy packs, and a bounded worktree controller. The next approved
20-item program must make graph reasoning historical and explainable, produce
deployable multi-service stacks, provide actionable security/compliance
intelligence, and operate continuously without weakening HITL or billing gates.

## 2. Safety invariants

1. Primary Markdown, lockfiles, signed registry metadata, ledgers, and human
   decisions remain authoritative; indexes and projections are rebuildable.
2. AI-extracted facts are proposals until mechanically linked to literal source
   evidence. AI confidence never substitutes for validation or approval.
3. Remote blueprint content requires explicit source configuration, hash
   verification, and signature verification before rendering.
4. Upgrades use a three-way base/current/target model and never overwrite a
   diverged user file without an explicit resolution.
5. Security/compliance output distinguishes confirmed evidence, heuristic
   findings, accepted risk, ignored fixtures, and unavailable external data.
6. Autonomous execution is default-off, sandboxed, budgeted, review-branch
   only, and cannot push, merge, expand permissions, or make billed calls
   without explicit policy and human authorization.

## 3. Deliverables

### F17 - Graph intelligence

Temporal snapshots and supersession, contradiction/duplicate analysis,
evidence-gated AI extraction, impact analysis, traceability coverage, graph
query/explanation commands, and bounded context packs for coding agents.

### F18 - Production factory

Signed local/remote blueprint registry, safe three-way upgrades, capability
resolution, production stack components, generated API/event/data contracts,
and federated multi-repository workspace graphs and plans.

### F19 - Security and compliance

Finding baselines and suppressions, a policy-pack SDK, offline SBOM/dependency/
license intelligence with optional vulnerability input, threat models, and
SOC 2/ISO 27001/GDPR/PCI control catalogs and evidence exports.

### F20 - Autonomous operations

A sandboxed event/schedule runtime with budgets, retries, approval queue,
provider-neutral PR seam, execution metrics, feedback capture, and bounded
policy learning. Direct default-branch mutation remains prohibited.

## 4. Acceptance gates

- F17: deterministic fixtures prove temporal history, contradictions,
  duplicates, evidence extraction, impact paths, coverage scores, queries and
  context budgets.
- F18: signed registry fixtures verify/reject content; upgrades retain
  divergence; composed production stacks and contracts run smoke gates;
  workspace plans traverse repositories.
- F19: fixtures prove baseline expiration, custom policies, SBOM/license data,
  threat paths and compliance evidence without requiring network.
- F20: simulated events and PR providers prove sandbox, budgets, retries,
  approval gates, metrics and feedback learning without pushing or merging.
- Release: `pytest -q`, `ruff check .`, `mypy hornero`, and
  `hornero validate --repair` are green.

## 5. Progress authority

Resume from `sdd/state/production-intelligence/PROGRESS.md` and
`sdd/tasks/index/production-intelligence.json`.

## 6. Log

- 2026-07-16 - Owner approved all 20 roadmap items for autonomous execution.
- 2026-07-16 - SPEC-006 and TASK-056 through TASK-075 created.
- 2026-07-16 - F17-F20 implementation complete; 308 tests, ruff and mypy green.
- 2026-07-16 - Project graph fresh with zero blocking findings: 1143 entities,
  1026 relations and 2172 provenance records.

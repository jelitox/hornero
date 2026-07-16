# Production intelligence program - progress checkpoint

Last updated: 2026-07-16
Authority: SPEC-006
Status: complete

## Resume protocol

1. Read `sdd/specs/SPEC-006-production-intelligence-platform.md`.
2. Read this checkpoint and `sdd/tasks/index/production-intelligence.json`.
3. Preserve all unrelated/user changes shown by `git status --short`.
4. Run the last verified gate below.
5. Continue the first `in_progress` task, otherwise the first dependency-ready
   pending task.
6. Update this file before ending a session or switching phases.

## Current task

All TASK-056 through TASK-075 and SPEC-006 are complete.

## Decisions

- Use stdlib-first, offline deterministic implementations and injected seams
  for signatures, vulnerability feeds, schedules, sandboxes and PR providers.
- Treat AI extraction as evidence-linked proposals; never persist unsupported
  facts as confirmed graph knowledge.
- Use hashes/HMAC signatures for the built-in registry seam; leave asymmetric
  signing pluggable without adding a mandatory crypto dependency.
- Preserve default-off autonomy and exact approval for risk, billing,
  permissions, compliance attestations, push and merge.

## Baseline

SPEC-005 completed immediately before this program:

```text
pytest -q: 291 passed
ruff check .: passed
mypy hornero: passed (56 source files)
graph: fresh, 0 blocking, 982 entities, 882 relations, 1864 provenance
```

## Completed

- F17: temporal snapshots/entity lineage, supersession edges, deterministic
  contradiction and duplicate candidates, verbatim-gated AI extraction,
  bounded impact traversal, traceability coverage, semantic query/explain and
  token-budgeted context packs.
- F18: signed registry envelopes, schema 2 base-preserving locks, three-way
  upgrades, capability resolution, production-service components, generated
  contracts and federated workspace impact plans.
- F19: fixture-aware findings, expiring owner/reason baselines, declarative
  policy SDK, offline SBOM/vulnerability intelligence, STRIDE models and four
  evidence-based compliance catalogs.
- F20: sanitized resource sandbox, persistent event/schedule ledger, signed
  replay-safe webhooks, budgets, exponential retries, approval queue,
  provider-neutral PR seam, metrics and bounded feedback weights.

## Last verified gate

```text
F17 focused pytest: 31 passed
F18 focused pytest: 15 passed
F19 focused pytest: 11 passed
F20 focused pytest: 33 passed
release pytest: 308 passed in 8.92s
ruff check .: passed
mypy hornero: passed (64 source files)
hornero validate --repair: fresh, 0 blocking, 4 historical warnings
graph: 295 pages, 558 edges, 1143 entities, 1026 relations, 2172 provenance
```

## Known pre-existing worktree changes

The worktree contains the complete uncommitted SPEC-005 implementation plus
older owner changes. Do not revert or overwrite them. SPEC-006 changes build on
that state.

## Next action

No remaining action for this approved 20-item program. A future cycle should
begin with a non-persisting scan, group exactly 20 evidence-backed items, and
request owner confirmation before implementation.

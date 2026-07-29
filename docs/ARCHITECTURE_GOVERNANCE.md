# Architecture knowledge and reuse governance

Hornero keeps a project-specific architecture corpus that coding agents can
query before they design or implement a feature. The core model is independent
of language and deployment style; profiles add the concerns relevant to a
monolith, REST service, website, worker, pipeline, library or distributed
system.

The governing rule is simple: Hornero owns approved architecture and
Multicoders receives a bounded, hashed copy. Provider output can propose a
change, but it cannot approve a component, decision or exception.

## Start a corpus

```bash
hornero architecture init --profile rest-service --profile python
```

Initialization is additive. It creates `sdd/architecture/project.yaml`, the
logical record directories and starter context documents, but refuses to
overwrite existing material. Projects that keep architecture elsewhere can
write `.hornero/architecture-layout.yaml`:

```yaml
schema: hornero.architecture.layout/v1
root: docs/architecture
```

The configured root must remain inside the project.

## Compose profiles

`project.yaml` separates system archetypes from technology:

```yaml
schema: hornero.architecture.project/v1
project:
  id: scheduling-api
  archetypes: [rest-service, background-worker]
stack:
  languages: [python]
  frameworks: [aiohttp]
profiles: [core, rest-service, background-worker, python, aiohttp]
governance:
  mode: advisory
  legacy_policy: warn
```

Built-in archetypes are `monolith`, `rest-service`, `website`,
`background-worker`, `pipeline`, `library` and `distributed-system`. Custom
profiles use a namespaced ID such as `acme:regulated-api`. An unavailable
profile is an error; Hornero never substitutes another profile.

`governance.mode` controls new findings:

- `off`: retain the corpus without enforcing new-spec fitness rules.
- `advisory`: report findings as warnings, except ambiguity and malformed
  records, which remain blocking.
- `enforced`: applicable violations block preflight.

`legacy_policy` is independently `ignore`, `warn` or `block`, allowing
brownfield projects to tighten governance incrementally.

## Register reusable capabilities

A capability describes an ability, not its implementation:

```yaml
schema: hornero.architecture.capability/v1
id: appointment-scheduling
title: Schedule appointments
interfaces: [calendar-api-v1]
providers:
  - component: shared-calendar
    mode: reuse
owner: scheduling-platform
status: active
```

The component record supplies ownership and literal evidence:

```yaml
schema: hornero.architecture.component/v1
id: shared-calendar
provides: [appointment-scheduling]
interfaces: [calendar-api-v1]
resources:
  - id: primary-database
    allocation: shared
owner: scheduling-platform
status: active
evidence:
  - path: src/calendar/service.py
    locator: SharedCalendar
```

Resolve it before designing a replacement:

```bash
hornero architecture query "calendar"
hornero architecture explain shared-calendar
hornero architecture resolve appointment-scheduling --json
```

Resolution is deterministic and returns `reuse`, `reuse_with_adapter`,
`extend`, `new_component` or `needs_human`. Every candidate and exclusion
contains its reason and evidence.

## Align specs before implementation

Governed specs carry a structured plan:

```yaml
architecture:
  profiles: [rest-service]
  domains: [scheduling]
  requests: [appointment-scheduling]
  reuses: [shared-calendar]
  extends: []
  introduces: []
  decisions: [ADR-012]
  quality_budgets:
    p95_latency_ms: 250
```

Check Definition of Ready and all applicable fitness functions:

```bash
hornero spec preflight SPEC-123
hornero architecture check --spec SPEC-123 --offline
hornero architecture check --all --offline --json
```

When the corpus is initialized, `hornero build` runs this preflight before
changing lifecycle state. The build brief includes the same versioned
`ArchitectureContext` for every independent provider. Context and evidence
carry hashes; stale `ArchitectureResult` payloads are rejected.

After dispatch, Hornero writes
`.hornero/runs/<run>/architecture-delta.json`. An undeclared or unregistered
deviation moves the spec to `needs_human` instead of silently reaching review.

## Inventory and brownfield adoption

```bash
hornero architecture inventory
hornero architecture inventory --propose --json
```

Inventory only produces `inferred` records. With `--propose`, the idempotent
result is written under `sdd/proposals/`; it never becomes approved
architecture automatically and never overwrites a reviewed proposal.

A practical adoption sequence is:

1. initialize profiles in advisory mode;
2. inventory repository evidence;
3. approve a glossary, domains and critical capabilities;
4. document existing debt with accountable, expiring exceptions;
5. require alignment on new specs;
6. move `legacy_policy` from `ignore` to `warn` to `block`.

## Exceptions and safety

Inspect exceptions with:

```bash
hornero architecture exception list
hornero architecture exception show EXCEPTION-ID
```

Exceptions require an owner, reason, scope, approver, creation date, expiry and
remediation reference. Expired exceptions fail closed. The architecture CLI is
read-only for approvals: autonomous execution may inventory, query, check and
record deltas, but it cannot create or extend an approved exception.

All default checks are offline. Profile-scoped rules prevent irrelevant
warnings—for example, a website without a worker profile is not checked for
queue retry semantics.

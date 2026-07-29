---
spec: SPEC-013
title: Universal architecture knowledge and capability-reuse governance
status: review
kind: new_feature
created: 2026-07-28
owner: javier@javierleon.dev
depends_on: [SPEC-004, SPEC-005, SPEC-011]
supersedes: []
sources:
  - owner-directive-20260728-universal-architecture-governance
  - field-observation-20260727-rapid-spec-development-reuse
acceptance_criteria:
  - "pytest -q"
  - "ruff check ."
  - "mypy hornero"
  - "hornero architecture check --all --offline"
  - "hornero validate --repair"
architecture:
  profiles: [monolith, library, python]
  domains: [developer-experience]
  requests: [architecture-governance]
  reuses: []
  extends: []
  introduces: [architecture-governance-core]
  decisions: []
  quality_budgets:
    offline_default: required
    deterministic_output: required
---

# SPEC-013 - Universal architecture knowledge and capability-reuse governance

## 1. Context

Specification-driven development can increase delivery speed while reducing
system-wide coherence. A team or coding agent can satisfy an isolated spec and
still duplicate an existing database pool, event bus, service, UI component,
domain concept or deployment primitive because the reusable architecture was
not discoverable in the context used to build the feature.

This is not limited to a particular product or technology. The same failure
appears differently across:

- monoliths, as duplicated infrastructure and eroded module boundaries;
- REST services, as inconsistent contracts, authentication and lifecycle;
- websites, as duplicate components, divergent design language and excess
  client dependencies;
- workers and pipelines, as competing queues, retry loops and checkpoints;
- libraries, as redundant abstractions and incompatible public APIs;
- distributed systems, as unowned interfaces and uncontrolled operational
  budgets.

Hornero therefore needs a technology-neutral architecture knowledge layer that
makes existing capabilities, constraints and recommended implementation paths
discoverable before development. Multicoders must consume that knowledge when
researching, designing, implementing or reviewing, without becoming a second
source of architectural truth.

Product-specific incidents such as connection-pool or event-bus proliferation
are conformance fixtures for this spec, not concepts embedded in the universal
model.

## 2. Goals and non-goals

### Goals

1. Represent architecture using a small universal ontology that applies to
   different system archetypes and technology stacks.
2. Maintain a queryable catalog of logical capabilities and the components
   that already provide them.
3. Require every governed spec to declare what it reuses, introduces and
   changes before implementation begins.
4. Compose universal, archetype, stack and project rules without hard-coding a
   single architecture style.
5. Detect likely reinvention, policy violations and resource-budget regressions
   with deterministic architecture fitness functions.
6. Give Multicoders a bounded, versioned architecture context pack before
   agent execution and ingest evidence-backed implementation results afterward.
7. Preserve ownership, decisions, exceptions and full provenance in Hornero's
   development graph.

### Non-goals

- Mandating microservices, monoliths, REST, a database, a frontend framework or
  any other particular architecture.
- Treating generated documentation, inferred relationships or agent consensus
  as approved architecture.
- Replacing source code, API schemas, database migrations, design systems or
  infrastructure definitions as their domain-specific sources of truth.
- Building a general-purpose enterprise CMDB.
- Automatically refactoring legacy systems or deleting suspected duplicates.
- Requiring complete documentation of an existing system before new work can
  begin.
- Allowing Multicoders or an LLM to approve architectural exceptions.

### Architecture alignment

- **Domain and owner:** `developer-experience`, owned by the Hornero
  maintainers.
- **Requested capability:** `architecture-governance`.
- **Introduced component:** `architecture-governance-core`; no pre-existing
  Hornero component provided the universal registry, preflight and fitness
  workflow when this spec was approved.
- **Interfaces:** the additive `architecture` and `spec preflight` CLI
  surfaces plus the versioned Multicoders context/result protocol.
- **Lifecycle and deployment:** repository-local, offline by default, with no
  daemon, remote service or new runtime resource.
- **Quality budgets:** deterministic output and zero network dependency for
  default checks.
- **Migration:** brownfield adoption begins in advisory mode and preserves
  existing project material; disabling governance leaves earlier workflows
  unchanged.
- **Rollback:** remove the additive command/package and architecture records;
  no primary source is rewritten by inventory or checks.

## 3. Responsibility boundary

### Hornero owns

- the architecture corpus, schema versions and layout mappings;
- capability/component discovery and deterministic matching;
- policy composition, fitness functions and quality budgets;
- spec preflight, Definition of Ready and Definition of Done;
- ADRs, exceptions, ownership, provenance and graph projection;
- architecture context packs and evidence validation.

### Multicoders owns

- provider selection and independent research/design/review fan-out;
- implementation and verification inside the authority granted by the caller;
- returning proposed architecture deltas and evidence to Hornero;
- surfacing disagreements and missing context without changing policy.

### Provider agents own

- their proposed solution and supporting evidence;
- explicit assumptions and unknowns;
- adherence to the supplied context and sandbox.

Provider output is advisory until Hornero can validate literal evidence and the
project's approval policy accepts the resulting proposal.

## 4. Universal architecture ontology

The core schema is versioned independently of profiles. Version 1 defines:

| Entity | Meaning |
|---|---|
| `System` | The product or bounded software system being described |
| `Domain` | A business or technical responsibility boundary |
| `Capability` | A logical ability the system needs, independent of implementation |
| `Component` | A module, service, package, UI element or infrastructure unit implementing behavior |
| `Interface` | A callable, HTTP, event, file, UI, CLI or other integration contract |
| `Dependency` | A directed need between architecture entities |
| `Resource` | A finite runtime or build resource such as connections, memory, threads or bundle bytes |
| `DataEntity` | A canonical concept and its ownership/storage classification |
| `Lifecycle` | Startup, readiness, steady-state, retry, shutdown and recovery behavior |
| `Constraint` | A rule that restricts an architecture or implementation choice |
| `Decision` | An approved ADR or equivalent choice with rationale and consequences |
| `QualityAttribute` | A measurable concern such as availability, security, accessibility or latency |
| `Owner` | A person, team or role accountable for an entity |
| `DeploymentUnit` | An independently built, released, deployed or distributed unit |
| `Exception` | A bounded, approved and expiring deviation from a rule |
| `Evidence` | A literal source locator supporting an architecture claim |

Core relations include:

```text
System --contains--> Component
System --deployed_as--> DeploymentUnit
Domain --owns--> Capability | DataEntity
Component --provides--> Capability
Component --exposes--> Interface
Component --depends_on--> Component | Interface | Resource
Capability --implemented_by--> Component
Interface --transports--> DataEntity
Component --has_lifecycle--> Lifecycle
Entity --constrained_by--> Constraint | Decision
Entity --measured_by--> QualityAttribute
Entity --owned_by--> Owner
Exception --waives--> Constraint
ArchitectureClaim --supported_by--> Evidence
```

Profiles may add entity types or relations under a namespaced extension, but
cannot redefine the semantics of core identifiers.

## 5. Architecture corpus and source precedence

### 5.1 Logical corpus

Hornero recognizes the following logical roles:

```text
architecture/
  project.yaml
  context.md
  glossary.md
  principles.md
  domains/
  capabilities/
  components/
  interfaces/
  data/
  deployments/
  decisions/
  patterns/
  quality/
  profiles/
  exceptions/
```

The physical paths are resolved through Hornero's layout manifest so a
repository may place them under `sdd/architecture`, `docs/architecture` or an
approved custom root. Commands and graph locators use logical roles rather than
hard-coded directories.

### 5.2 Sources of truth

Hornero does not copy authoritative domain artifacts into prose when a better
source exists. It links and projects:

- code/module manifests for components and dependencies;
- OpenAPI, AsyncAPI, GraphQL, protobuf or equivalent interface contracts;
- schema/migration files for persisted data;
- package and lock files for external dependencies;
- deployment manifests for runtime topology;
- design-system manifests for reusable visual components and tokens;
- Markdown/YAML architecture records for concepts not encoded elsewhere.

When sources disagree, precedence is:

```text
approved Decision and explicit project policy
  → authoritative machine-readable contract
  → approved architecture record
  → approved spec
  → evidence-backed repository inference
  → agent proposal
```

Contradictions are retained and surfaced. Lower-precedence evidence never
silently overwrites a higher-precedence source.

## 6. Project manifest and composable profiles

Every governed project may declare:

```yaml
schema: hornero.architecture.project/v1
project:
  id: example
  archetypes: [rest-service, background-worker]
stack:
  languages: [python]
  frameworks: [aiohttp]
profiles:
  - core
  - rest-service
  - background-worker
  - python
  - aiohttp
governance:
  mode: advisory
  legacy_policy: warn
```

Archetypes and profiles are composable, not a closed enum. Hornero ships a
small built-in catalog and projects may add namespaced profiles.

Initial built-in archetype profiles are:

| Profile | Example concerns |
|---|---|
| `monolith` | module boundaries, composition root, shared infrastructure and process lifecycle |
| `rest-service` | HTTP contracts, errors, auth, idempotency, timeouts and compatibility |
| `website` | design system, accessibility, navigation, SEO, responsive behavior and performance budgets |
| `background-worker` | delivery semantics, retries, idempotency, checkpoints and shutdown |
| `pipeline` | lineage, scheduling, partial recovery, data contracts and reproducibility |
| `library` | public API, semantic compatibility, deprecation and dependency surface |
| `distributed-system` | ownership, service contracts, failure boundaries and operational budgets |

Stack profiles such as `python`, `aiohttp`, `typescript` or `nextjs` translate
generic constraints into stack-aware detection and remediation. They remain
optional extensions; the core functions without them.

An unavailable profile produces a visible validation finding. Hornero never
silently substitutes a different profile.

## 7. Capability and component registry

### 7.1 Capability record

A capability is expressed independently of its provider:

```yaml
schema: hornero.architecture.capability/v1
id: persistent-user-preferences
title: Persist user preferences
domain: identity-experience
requirements:
  durability: user-scoped
  consistency: eventual
providers:
  - component: shared-settings-repository
    profiles: [monolith, rest-service]
    interfaces: [settings-repository-v1]
owner: platform
status: active
```

### 7.2 Component record

A component describes an implementation:

```yaml
schema: hornero.architecture.component/v1
id: shared-settings-repository
provides: [persistent-user-preferences]
interfaces: [settings-repository-v1]
lifecycle: application-managed
resources:
  - id: primary-database
    allocation: shared
owner: platform
evidence:
  - path: src/infrastructure/settings.py
    locator: SharedSettingsRepository
```

### 7.3 Deterministic reuse resolution

Before suggesting a new component, Hornero:

1. normalizes the requested logical capabilities;
2. queries active providers and their evidence;
3. filters by project/profile compatibility and hard constraints;
4. compares interfaces, lifecycle, ownership and quality budgets;
5. returns one of:
   `reuse`, `reuse_with_adapter`, `extend`, `new_component`, or
   `needs_human`;
6. explains every included and excluded candidate with graph paths.

An LLM may suggest search terms or rank already eligible candidates, but it
cannot remove deterministic candidates or declare that no reusable capability
exists without evidence.

Creating `new_component` requires:

- a missing-capability or incompatibility explanation;
- proposed owner and lifecycle;
- interfaces and affected domains;
- resource and quality-budget impact;
- tests and migration/rollback strategy;
- an ADR when the component introduces a shared infrastructure primitive,
  public contract or cross-domain dependency.

## 8. Layered policy and exception model

Rules compose in this order:

```text
universal
  → archetype profile
  → stack profile
  → project policy
  → approved bounded exception
```

Higher-specificity layers may strengthen a rule. They may weaken it only
through an explicit `Exception` record permitted by the parent rule.

A rule contains:

```yaml
schema: hornero.architecture.rule/v1
id: ARCH-DEPENDENCY-001
title: Architecture dependencies require purpose and ownership
applies_when: entity.kind == "Dependency"
severity: blocking
check:
  engine: graph-query
  query: dependency_without_owner_or_purpose
remediation: Register the dependency and its accountable owner.
exception:
  allowed: true
  maximum_days: 30
```

Exceptions require owner, reason, scope, approver, creation/expiry dates and a
remediation reference. Expired exceptions fail closed. Autonomous mode cannot
create, extend or approve one.

## 9. Spec architecture-alignment contract

Governed specs add a structured frontmatter block:

```yaml
architecture:
  profiles: [rest-service]
  domains: [scheduling]
  requests: [appointment-scheduling]
  reuses: [shared-calendar, authenticated-handler]
  extends: []
  introduces: []
  decisions: [ADR-012]
  quality_budgets:
    p95_latency_ms: 250
```

The corresponding human-readable section records:

1. affected domains and owners;
2. requested capabilities;
3. reusable candidates considered and selection rationale;
4. components/interfaces/resources reused or extended;
5. infrastructure, public contracts or canonical concepts introduced;
6. lifecycle and deployment impact;
7. quality and operational budgets;
8. decisions, exceptions and open questions;
9. migration, compatibility and rollback expectations.

### Definition of Ready

A spec is ready for `approved` only when:

- required architecture profiles resolve;
- domain language is consistent with the glossary;
- requested capabilities have a reuse-resolution result;
- introduced components have the required justification and owner;
- applicable blocking constraints have no unapproved violation;
- resource/quality impacts are declared where the selected profiles require
  them;
- unresolved high-impact contradictions are `needs_human`.

### Definition of Done

A spec is ready for `done` only when:

- implementation evidence matches the declared reuse plan or records an
  approved deviation;
- interfaces, dependencies and ownership are graph-connected;
- applicable fitness functions pass;
- architecture records and ADRs introduced by the work exist;
- tests verify capability behavior and required quality budgets;
- the actual implementation delta has been compared with the approved spec.

Projects adopting governance incrementally may configure legacy specs as
`ignore`, `warn` or `block`. New specs default to `block` once architecture
governance is enabled.

## 10. Architecture preflight and implementation-delta workflow

### Preflight

```text
Requirement/spec
  → resolve project profiles
  → identify domains and logical capabilities
  → query catalog and repository evidence
  → compute reuse candidates and constraints
  → evaluate Definition of Ready
  → build bounded ArchitectureContext
```

The preflight is deterministic and offline by default. Missing information is
represented as an unknown, never inferred as permission to create a new
primitive.

### Post-build

```text
Implementation
  → inventory changed architecture evidence
  → compare approved vs actual entities/relations
  → run applicable fitness functions
  → produce ArchitectureDelta
  → accept, reject or escalate each deviation
  → reindex graph
```

The delta distinguishes added, removed, reused, extended and behaviorally
changed architecture entities. It never rewrites primary documentation without
the existing approval/write policy.

## 11. Hornero/Multicoders protocol

Hornero supplies a versioned `ArchitectureContext` in advisory and build
briefs:

```json
{
  "schema": "hornero.architecture.context/v1",
  "project": {"id": "example", "profiles": ["rest-service"]},
  "requested_capabilities": ["appointment-scheduling"],
  "reuse_candidates": [
    {
      "component": "shared-calendar",
      "resolution": "reuse",
      "evidence": ["src/calendar.py#SharedCalendar"]
    }
  ],
  "constraints": [
    {"id": "ARCH-AUTH-001", "source": "ADR-012", "quote": "..."}
  ],
  "forbidden_duplications": ["database-access"],
  "quality_budgets": {"p95_latency_ms": 250},
  "unknowns": []
}
```

Every source entry includes a locator and content hash. Multicoders gives the
same neutral architecture context to independent first-pass providers under
SPEC-011.

Multicoders returns:

```json
{
  "schema": "hornero.architecture.result/v1",
  "context_hash": "...",
  "reused": [],
  "extended": [],
  "introduced": [],
  "deviations": [],
  "evidence": [],
  "unknowns": []
}
```

Hornero rejects malformed, stale or mismatched context hashes. Multicoders may
propose new capabilities, patterns or decisions, but cannot register or
approve them directly.

## 12. Architecture fitness functions

Fitness functions are profile-scoped, deterministic controls. Engines may
include:

- graph queries over architecture/code/deployment relations;
- repository AST or semantic analyzers;
- contract/schema compatibility checks;
- allowlisted offline commands;
- test-result and artifact ingestion;
- baseline/delta budget comparisons.

Examples by profile:

| Profile | Example fitness function |
|---|---|
| universal | every dependency and public interface has purpose, evidence and owner |
| monolith | infrastructure creation occurs only through registered composition components |
| rest-service | routes match declared contracts and auth/error policies |
| website | reused visual components exist in the design-system catalog; accessibility and bundle budgets pass |
| worker | every background task declares retry, idempotency and shutdown behavior |
| library | public API removal has an approved compatibility/deprecation decision |
| distributed-system | cross-unit calls declare timeout, failure policy and accountable owners |

Technology-specific checks such as connection counts apply only when the
corresponding resource/profile is active. A website without a database is not
warned about database pools.

Findings include rule ID, severity, affected entity, literal evidence,
remediation, profile origin and exception eligibility. Baselines may suppress
legacy debt only with an owner and expiry; they cannot hide new regressions.

## 13. User-facing contract

The initial Hornero surface is:

```text
hornero architecture init [--profile NAME ...]
hornero architecture inventory [--propose] [--json]
hornero architecture query TEXT [--json]
hornero architecture explain ENTITY_ID [--json]
hornero architecture resolve CAPABILITY_ID [--spec SPEC-NNN] [--json]
hornero architecture check [--spec SPEC-NNN | --all] [--offline] [--json]
hornero architecture diff [--base REF | --commit SHA] [--json]
hornero architecture exception list|show
hornero spec preflight SPEC-NNN [--json]
```

`init` is additive and refuses to overwrite existing architecture material.
`inventory --propose` writes derived proposals to a review area, not approved
records. `query` and `explain` always distinguish authoritative facts,
evidence-backed inference and proposals.

Exception creation/approval uses the existing HITL-controlled change path; the
read-oriented architecture command does not expose an autonomous approval
shortcut.

## 14. Graph and provenance contract

Architecture entities join, rather than replace, the existing semantic graph:

```text
Requirement --requests--> Capability
Requirement --affects--> Domain
Requirement --plans_to_reuse--> Component
Requirement --introduces--> Component | Interface | DataEntity
Requirement --constrained_by--> Decision | Constraint
Component --provides--> Capability
Component --exposes--> Interface
Component --depends_on--> Component | Resource
Component --deployed_as--> DeploymentUnit
ArchitectureRule --applies_to--> Profile | Entity
FitnessFinding --violates--> ArchitectureRule
FitnessFinding --supported_by--> Evidence
Exception --waives--> ArchitectureRule
ArchitectureDelta --deviates_from--> Requirement
```

Every architecture entity/relation records source path, content hash, locator,
origin, confidence class and observation time. Inferred entities cannot use the
same authority class as explicit records.

Reindexing is deterministic. Removed evidence produces stale/tombstoned claims
and validation findings rather than silently retaining a false active fact.

## 15. Safety and autonomous-mode policy

Autonomous mode may:

- inventory repository evidence;
- create derived proposals and context packs;
- query capabilities and evaluate deterministic rules;
- run allowlisted offline fitness functions;
- record implementation deltas and update derived graph projections.

It may not:

- approve a spec, ADR, architecture record or exception;
- invent an owner or resolve a domain-definition conflict;
- delete or replace a component because it appears duplicated;
- mutate code solely to satisfy an inferred architectural preference;
- weaken profiles, rules, budgets or Definition-of-Ready gates;
- send proprietary architecture context to a remote provider without the
  configured data policy;
- turn advisory provider consensus into approval.

Architecture context uses the same bounding, redaction, billing and provider
isolation rules as SPEC-011.

## 16. Incremental adoption and migration

Hornero supports brownfield systems without requiring a documentation
big-bang:

1. initialize the project manifest and select profiles;
2. inventory repository sources into evidence-backed proposals;
3. approve a minimal glossary, domains and critical capabilities;
4. establish baselines for known debt with owners and expiry;
5. enforce architecture alignment for new specs;
6. progressively promote verified proposals into explicit records;
7. tighten `legacy_policy` from `ignore` to `warn` to `block`.

Inventory is idempotent. Manual edits to approved records are preserved.
Profile/schema upgrades use a versioned migration with preview and rollback;
unknown fields fail closed rather than being discarded.

## 17. Implementation phases

| Phase | Deliverable | Deterministic gate |
|---|---|---|
| F33 - universal model and corpus | Versioned core ontology, configurable layout, project manifest, parsers and explicit/inferred authority classes | Fixtures for a monolith, REST service and website produce valid core entities without requiring irrelevant profiles |
| F34 - profiles and reuse resolution | Built-in archetype profiles, namespaced custom profiles, capability/component registry and explainable matcher | Golden fixtures resolve `reuse`, `reuse_with_adapter`, `extend`, `new_component` and conflicts with stable explanations |
| F35 - spec governance | Architecture frontmatter/section parsing, preflight, Definition of Ready/Done and architecture context packs | A spec reusing an existing component passes; an unjustified duplicate or missing owner fails with exact graph evidence |
| F36 - fitness and deltas | Rule engines, layered policy, budgets, baselines/exceptions and post-build ArchitectureDelta | Profile-scoped tests prove irrelevant rules do not run, new regressions fail and expired exceptions stop waiving findings |
| F37 - Multicoders and graph integration | Context/result v1 protocol, neutral provider fan-out integration, architecture entities/relations, CLI and operator docs | Fake providers receive identical hashed context; result evidence traverses spec -> capability -> component -> delta/finding with provenance |

## 18. Test specification

- Default tests are offline and use fixture repositories; no provider, network,
  database, browser or deployment platform is required.
- Golden projects cover at least a monolith, REST service, website, worker and
  library.
- The same logical capability implemented with different technologies maps to
  one core capability and technology-specific components.
- Profile-composition fixtures cover strengthening, conflict, unknown profile,
  project override and expiring exception behavior.
- Reuse fixtures prove an existing component cannot disappear from candidate
  results because an LLM omits it.
- Brownfield fixtures prove legacy warnings do not block until configured, but
  new regressions do.
- Round-trip tests preserve unknown schema fields during supported migrations.
- Graph tests require provenance for every architecture claim and reject
  dangling or authority-escalated relations.
- Multicoders protocol tests verify context hashes, neutral first-pass briefs,
  malformed-result rejection and zero automatic approval.

## 19. Open questions

- OQ1. Should built-in profiles ship inside Hornero core or as separately
  versioned policy packs? Separate packs improve evolution but complicate
  compatibility for the first release.
- OQ2. Which machine-readable format should be primary for architecture
  records: YAML documents, JSON Schema-validated YAML, or a small manifest plus
  Markdown? Human review favors Markdown; deterministic tooling favors schemas.
- OQ3. Should `architecture inventory` use language adapters in Hornero or
  reuse Multicoders research providers for non-authoritative proposals?
- OQ4. What minimum set of profile-independent quality attributes should be
  universal rather than opt-in?
- OQ5. Should capability matching support organization-wide registries in F34,
  or begin repository/workspace-local and federate later?

## 20. Log

- 2026-07-29 - F33-F37 implemented and moved to `review`: universal records,
  profiles, reuse resolution, spec preflight, fitness checks, deltas,
  Multicoders context/result validation, CLI, graph projection and operator
  documentation. Isolated publish gates passed with 353 tests, Ruff, mypy,
  architecture preflight/check and graph validation at zero blocking findings.
- 2026-07-29 - Owner explicitly requested execution. SPEC-013 was approved
  and moved to `building`; implementation is running directly in the Hornero
  repository because no real Multicoders dispatch backend is configured.
- 2026-07-27 - Field discussion identified rapid spec-driven delivery that
  satisfied local requirements while duplicating database pools, event buses,
  lifecycle logic and domain concepts. These observations motivated reuse
  governance but remain product-specific examples.
- 2026-07-28 - Owner clarified that Hornero and Multicoders must support
  heterogeneous projects including monoliths, REST services and websites
  rather than encode one backend architecture.
- 2026-07-28 - SPEC-013 proposed a universal ontology, composable profiles,
  capability registry, layered policy, architecture-aligned specs, fitness
  functions and a strict Hornero-governance/Multicoders-execution boundary.

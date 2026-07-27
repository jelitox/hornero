---
spec: SPEC-012
title: Grounded visual mockups as governed development artifacts
status: review
kind: new_feature
created: 2026-07-26
owner: javier@javierleon.dev
depends_on: [SPEC-005, SPEC-009, SPEC-011]
supersedes: []
sources:
  - owner-directive-20260726-grounded-visual-mockups
  - codex-image-generation-capability-audit-20260726
acceptance_criteria:
  - "pytest -q"
  - "ruff check ."
  - "mypy hornero"
  - "python scripts/changelog.py validate"
---

# SPEC-012 - Grounded visual mockups as governed development artifacts

## 1. Context

Design mockups are useful only when they reflect the product that will
actually be built. A generic prompt can contradict approved navigation,
feature scope or domain language; a from-scratch render can also discard the
real application's chrome and visual system. Hornero therefore needs a
mockup workflow grounded in approved specs and decisions, preferably editing a
real screenshot, with Codex image generation acting as a provider rather than
the source of product truth.

The workflow extends SPEC-011's provider isolation and audit model, but mockup
generation is a distinct artifact-producing capability. It receives narrowly
scoped write access to a scratch artifact directory, never to source files.

## 2. Goals and non-goals

### Goals

1. Generate one raster mockup per explicitly named view using real repository
   decisions and product context.
2. Use an existing screenshot as the edit target so unchanged application
   chrome and visual language remain recognizable.
3. Validate, hash, manifest and graph every input, provider run and generated
   artifact.
4. Support iterative refinement through the provider's existing session.
5. Deliver local artifacts to supported clients, including Telegram when
   Multicoders is the transport.

### Non-goals

- Treating generated text, icons, spacing or pixels as an approved design
  system.
- Committing exploratory PNGs or promoting them into approved specs
  automatically.
- Replacing frontend implementation, accessibility review or design QA.
- Sending private screenshots to an API without an explicit provider and data
  policy decision.
- Generating a mockup when hard constraints conflict or the required reference
  image cannot be safely read.

## 3. User-facing contract

```text
hornero mockup create --spec SPEC-NNN --request TEXT
                      --screenshot PATH
                      --view NAME[=FILENAME.png] [--view ...]
                      [--provider codex] [--autonomous] [--json]
hornero mockup show RUN_ID [--json]
hornero mockup deliver RUN_ID [--transport telegram|local]
hornero mockup refine RUN_ID --instruction TEXT [--screenshot PATH]
hornero mockup promote RUN_ID --artifact NAME --destination PATH
```

`create` requires a screenshot by default. `--from-scratch` is a separate,
explicit mode and the manifest records that no visual reference was supplied.
Each view has one exact, path-safe PNG filename declared before provider
execution.

`promote` is always HITL. It copies a selected artifact into a tracked
destination only after the user has reviewed it; autonomous mode cannot invoke
or imply promotion.

## 4. Grounding pipeline

Before invoking a provider, Hornero assembles a `MockupBrief`:

1. **Request** - the user's transformation request, without adding a preferred
   design solution.
2. **Reference image** - the screenshot path, SHA-256, dimensions, media type
   and a human-readable sentence naming the area to transform.
3. **Decided constraints** - verbatim quotes from approved specs, ADRs/DRs and
   accepted proposals, each with a source locator and content hash.
4. **Product context** - at most the bounded context needed to explain the
   product, screen and domain vocabulary.
5. **Named views** - one independent output requirement and exact filename per
   requested state/view.
6. **Visual language** - observable properties from the screenshot such as
   header/card treatment, accent colors, radius and density, phrased as
   preservation constraints rather than an invented redesign.
7. **Content realism** - reuse visible entities when safe and otherwise use
   domain-plausible placeholders, never lorem ipsum or real undisclosed PII.
8. **Provider report** - require a final list of files generated, assumptions
   made and open questions.

Approved decisions are hard constraints. Proposed material is labeled as such
and cannot override an approved source. A conflict produces `needs_human`
before image generation.

## 5. Screenshot and data safety

1. Paths are resolved inside the repository or an explicitly configured input
   root; symlinks and traversal cannot escape that boundary.
2. Only allowlisted image media types and bounded file sizes/dimensions are
   accepted. The decoder validates bytes rather than trusting the extension.
3. The user is warned when a screenshot may contain people, credentials,
   customer data or other sensitive content. Configurable redaction/cropping
   occurs before provider invocation and the sanitized image receives its own
   hash and provenance relation.
4. Original screenshots are not copied into tracked repository paths.
5. Provider data handling is visible before execution. A remote/API provider
   requires explicit opt-in; there is no silent API fallback.
6. Textual prompts, result messages and manifests pass through Hornero
   redaction. Binary artifacts are treated as sensitive local outputs by
   default.

## 6. Provider execution

The first provider adapter targets Codex's installed image-generation
capability:

- new runs use an attached screenshot, workspace-write sandbox and a dedicated
  output directory;
- the provider prompt names every exact expected output file;
- all repository context is read-only and output writes are contained in the
  run directory;
- refinement resumes the recorded provider session and supplies the writable
  sandbox through the resume command's supported configuration override;
- a new screenshot may be attached to a refinement when the provider supports
  it; otherwise the run fails clearly rather than discarding the image;
- ChatGPT-backed CLI authentication is the default. API-backed image generation
  is a separately configured, budgeted mode and never a fallback.

The adapter must discover capabilities instead of relying on a fixed CLI
version string. Missing image generation, authentication or session-resume
support produces a typed failure and preserves the brief for later retry.

## 7. Artifact workspace and validation

Runtime files live in:

```text
.hornero/artifacts/mockups/<run_id>/
  brief.json
  manifest.json
  references/
  outputs/
  provider-result.txt
```

This directory is derived, local and gitignored. Provider write access is
limited to a newly created run directory. Expected filenames are normalized,
collision-free and cannot contain path separators.

After execution Hornero validates:

- exactly one output exists for every requested view and no undeclared output
  is accepted into the manifest;
- every artifact is a non-empty, decodable PNG within configured byte and
  dimension limits;
- generated files remain inside the run directory and are regular files;
- SHA-256, dimensions, provider/session metadata and source hashes are stored;
- the result report lists assumptions and open questions;
- missing views, malformed images or unexpected files produce a partial or
  failed run, never a false success.

Raster artifacts may contain garbled text, inconsistent icons or other
generation defects. Delivery labels these as rendering artifacts rather than
design intent and preserves the open questions for refinement.

## 8. Delivery and refinement

Local delivery returns artifact paths plus manifest metadata. A Multicoders
Telegram adapter must support multipart upload of a local PNG, not only remote
URLs or platform file IDs, and must enforce Telegram size/type limits before
network access.

Delivery is a separate event from generation and records transport, recipient
scope, artifact hash, result and timestamp. It never sends an image to a chat
or external service that the user did not select.

`refine` keeps the original brief, screenshots, constraints and provider
session, appends a neutral refinement instruction and writes new versioned
artifacts. It does not overwrite prior outputs. Each generation records
`refines` and `supersedes_visual` relations while preserving the complete
lineage.

## 9. Autonomous-mode policy

With `--autonomous`, Hornero may:

- discover and quote approved context;
- validate/redact inputs;
- create the isolated artifact workspace;
- invoke the configured provider;
- retry transient failures;
- validate outputs, build the manifest, update the graph and deliver only to
  the already selected local destination.

It may not:

- infer consent to send a screenshot to a remote provider or chat;
- use a billed API, add credentials or increase data retention;
- exceed configured view, retry, wall-clock, output-byte or cost budgets;
- resolve contradictory approved constraints;
- mark a mockup approved, change a spec, edit product code, commit an image,
  open/merge a PR or deploy.

The defaults are a bounded number of views and retries, zero API cost budget
and no external delivery. Any limit breach ends `needs_human` with partial
artifacts retained and labeled.

## 10. Development-graph contract

The semantic graph projects:

```text
Requirement --requested--> MockupRun
MockupRun --grounded_by--> Spec | Decision | ProductContext
MockupRun --uses_reference--> ReferenceImage
ReferenceImage --sanitized_as--> ReferenceImage
MockupRun --produced_by--> ProviderRun
MockupRun --produced--> VisualArtifact
VisualArtifact --represents--> MockupView
VisualArtifact --satisfies--> Criterion
VisualArtifact --refines--> VisualArtifact
VisualArtifact --delivered_by--> DeliveryEvent
VisualArtifact --promoted_as--> RepositoryArtifact
```

Every binary node includes content hash, media type, dimensions, storage
classification and provenance. Every constraint relation points to the exact
source locator. Deleted local runtime files leave tombstoned metadata rather
than dangling graph relations.

## 11. Implementation phases

| Phase | Deliverable | Deterministic gate |
|---|---|---|
| F29 - grounded brief | Screenshot validator, approved-context collector, verbatim constraint model, view/filename contract and conflict detection | Golden brief quotes exact source spans; traversal, invalid images, PII fixtures and conflicting decisions fail closed |
| F30 - image artifact adapter | Codex capability discovery, isolated writable run directory, image attachment, bounded execution and output validation | Fake provider PNG fixtures prove exact view count, containment, hashes, malformed-output handling and zero API fallback |
| F31 - refinement and delivery | Session resume, immutable versions, local delivery and Multicoders Telegram multipart upload | Refinement preserves prior artifacts/session lineage; transport mock receives the selected bytes once and rejects oversize files before sending |
| F32 - graph and operations | Mockup entities/relations, manifests, show/promote commands, retention and operator documentation | Fixture traverses requirement -> run -> reference/provider -> artifact -> delivery with provenance; promotion remains HITL |

## 12. Test specification

- All default tests use fake providers and minimal valid PNG fixtures; no image
  model, network or installed Codex binary is required.
- Context tests prove only approved decisions become hard constraints and
  quoted text is byte-for-byte traceable to its source.
- Security tests cover traversal, symlinks, decompression bombs, oversized
  dimensions/files, spoofed extensions, embedded sensitive text metadata and
  unexpected output files.
- Billing tests prove missing CLI capability never activates an API provider
  and an API mode requires explicit configuration plus budget.
- Resume tests prove the writable sandbox is configured on the resume path and
  provider session IDs are stable.
- Graph tests require provenance for every mockup entity and relation and
  validate behavior after local artifact pruning.
- Optional visual smoke tests are manual/local, marked separately and excluded
  from deterministic CI.

## 13. Open questions

- OQ1. Which image redaction implementation is acceptable as the first
  optional dependency, and which sensitive-content classes require a hard stop
  instead of a warning?
- OQ2. Should approved mockups live in `sdd/artefacts/`, `docs/`, or a
  configurable design-system path after explicit promotion?
- OQ3. Should Telegram delivery be implemented in Multicoders first or behind
  a generic Hornero `ArtifactDeliveryPort` that Multicoders can consume?

## 14. Log

- 2026-07-26 - Owner requested a reusable mockup command that gives Codex the
  approved specs and a real system screenshot, generates one image per view
  and supports iterative refinement.
- 2026-07-26 - Capability audit confirmed Codex CLI image attachment, output
  capture, writable sandbox and resumable sessions; repository audit confirmed
  that Hornero can supply bounded semantic context and provenance while
  Multicoders still needs local-file Telegram upload.
- 2026-07-26 - Owner authorized implementation and publication across Hornero
  and Multicoders. F29-F32 implemented with bounded screenshot input,
  isolated output workspaces, PNG validation, resume/refinement, multipart
  Telegram delivery, promotion HITL and graph lineage; status moved to review
  pending PR.

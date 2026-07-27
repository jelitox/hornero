# Independent advisory and grounded mockups

Hornero owns product truth and audit; Multicoders owns provider processes.
Configure the bridge in `.hornero/config.yaml`:

```yaml
multicoders:
  command: [python, -m, multicoders]
  providers: [codex, claude, gemini]
  minimum_quorum: 2
  timeout_seconds: 600
  max_context_bytes: 200000
  max_views: 4
```

The command must resolve an installation containing the `perspective` and
`mockup` JSON protocol commands. Official provider CLIs use their own login
sessions. API keys are removed from each provider child environment unless a
separate, explicit API mode is selected; there is no billed fallback.

## Independent perspectives

```bash
hornero consult review --spec SPEC-011 --uncommitted
hornero consult brainstorm --spec SPEC-011 --question "Which boundary is simplest?"
hornero consult research --spec SPEC-011 --question "Cross-check this assumption"
hornero consult show consult-000001 --json
hornero consult triage consult-000001 finding-abcd CONFIRM \
  --reason "Verified against the approved ADR"
hornero consult resume consult-000001 --question "Re-check the timeout finding"
```

Hornero quotes the selected spec and linked decisions verbatim, hashes every
evidence item and optionally attaches a bounded git diff. Multicoders starts
all phase-one providers concurrently with the same brief hash and read-only
sandbox. Peer output is unavailable until all slots close. Quorum failure
returns `needs_human`; it never fabricates a synthesis.

Every finding stays in the ledger with `CONFIRM`, `REJECT` or `ESCALATE`.
Triage never deletes a minority opinion. `--autonomous` only removes the need
to wait at the terminal; it requires `autonomy.enabled: true` and cannot edit
code, change quorum, enable billing or merge.

## Grounded visual artifacts

```bash
hornero mockup create \
  --spec SPEC-012 \
  --request "Add the approved scheduling views" \
  --screenshot docs/current-screen.png \
  --view calendar=calendar.png \
  --view details=details.png

hornero mockup show mockup-000001 --json
hornero mockup refine mockup-000001 \
  --instruction "Increase density and preserve the current sidebar"
hornero mockup deliver mockup-000002 --transport local
hornero mockup promote mockup-000002 visual-abc123 \
  --destination docs/artefacts/scheduling-calendar.png
```

A screenshot is required unless `--from-scratch` is explicit. It must live
inside the repository so it cannot escape the audited input boundary.
Multicoders copies it into an isolated `.hornero/artifacts/mockups/<run>/`
workspace, grants write access only there, asks Codex image generation for one
exact PNG per named view, and validates signatures, dimensions, byte limits,
hashes and undeclared files.

Exploratory images are ignored runtime data. Only the explicit `promote`
command copies one reviewed artifact into a tracked repository destination.
Promotion refuses path traversal and overwrites.

## Development graph

`hornero reindex` projects advisory runs, provider perspectives, evidence,
findings, dispositions, mockup runs, references, visual artifacts, refinements
and promotions from the ledger. The create/refine/triage/promote commands
reindex automatically, so `hornero knowledge relations <entity>` can follow
the complete lineage immediately.

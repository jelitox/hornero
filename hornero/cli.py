"""hornero CLI (SPEC-001 §10). MVP surface:

    hornero init                      scaffold .hornero/ + the sdd/ layout in an existing repo
    hornero status                    spec counts by state, pending inbox, index health
    hornero reconcile [--dry-run]     (F2)
    hornero build [SPEC-ID ...]       (F3)
    hornero reindex                   (F4)
    hornero report [--only <name>]    (F5)

stdlib argparse only — no CLI framework dependency.
"""

import argparse
import json
import sys
from pathlib import Path

from hornero.adapters.inbox import InboxSource
from hornero.config import ConfigError, load_config
from hornero.lifecycle import SpecCorpus, Status
from hornero.memory.ledger import Ledger

DEFAULT_CONFIG = """\
# hornero configuration (SPEC-001 §4)
signal_source: inbox          # SignalSource adapter
tracker: repo                 # TrackerPort adapter
dispatch:
  backend_order: [mock]       # never auto-includes 'api' (opt-in only)
criterion_allowlist: [pytest, ruff, mypy, python]
models: {}
providers: {}
autonomy:
  enabled: false              # explicit opt-in; isolated branches only
  max_changes: 1
  allowed_risk: [low]
  gates: [[pytest, -q]]
  sandbox_command: []         # e.g. [bwrap, ...]; required by scheduled run
  require_sandbox: false
"""

_HORNERO_DIRS = ("inbox", "processed", "knowledge")
_GITIGNORE_LINES = (
    ".hornero/ledger.db*",  # includes SQLite -wal/-shm siblings
    ".hornero/runs/",       # traces: gitignored unless runs.commit opts in
    ".hornero/cache/",
)


def _cmd_init(root: Path, *, no_sdd: bool = False, no_wiki: bool = False) -> int:
    from hornero.layout import SDD_STATE_DIRS
    from hornero.sdd_toolkit.install import scaffold_dirs

    hornero_dir = root / ".hornero"
    for name in _HORNERO_DIRS:
        d = hornero_dir / name
        d.mkdir(parents=True, exist_ok=True)
        (d / ".gitkeep").touch()
    scaffold_dirs(root, SDD_STATE_DIRS)  # SPEC-002 §2: SDD layout is native

    config = hornero_dir / "config.yaml"
    if not config.exists():  # never overwrite an existing config
        config.write_text(DEFAULT_CONFIG, encoding="utf-8")

    project_marker = hornero_dir / "project.json"
    if not project_marker.exists():
        project_marker.write_text(
            json.dumps(
                {"root": str(root.resolve()), "schema": 1},
                indent=2,
                sort_keys=True,
            ) + "\n",
            encoding="utf-8",
        )

    gitignore = root / ".gitignore"
    lines = gitignore.read_text(encoding="utf-8").splitlines() if gitignore.exists() else []
    missing = [li for li in _GITIGNORE_LINES if li not in lines]
    if missing:
        gitignore.write_text("\n".join([*lines, *missing]) + "\n", encoding="utf-8")

    Ledger(hornero_dir / "ledger.db").close()  # idempotent schema init
    print(f"initialized hornero in {root}")

    # SPEC-003 §8: agents entering the repo must find hornero's map.
    from hornero.instructions import inject

    for name in inject(root):
        print(f"instruction section written: {name}")

    # SPEC-003 §3: init offers the wiki (offline-safe: a hint, never an LLM
    # call); SPEC-002 §8: toolkit install is init's final step, skippable.
    if not no_wiki and not (root / "wiki").is_dir():
        print("hint: run 'hornero wiki init' to create the agent-facing wiki")
    if no_sdd:
        return 0
    try:
        upstream = load_config(root).sdd_upstream
    except ConfigError:
        upstream = ""
    if upstream:
        from datetime import datetime, timezone

        from hornero.sdd_toolkit.install import install

        return install(
            root, upstream, load_config(root).sdd_ref,
            synced_at=datetime.now(timezone.utc).isoformat(),
        )
    print("hint: run 'hornero sdd install --from <toolkit-repo>' to add the SDD toolkit")
    return 0


def _cmd_status(root: Path) -> int:
    try:
        load_config(root)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 1

    from hornero.layout import specs_dir

    corpus = SpecCorpus(specs_dir(root))
    counts = corpus.counts_by_status()
    print(f"specs: {len(corpus.docs)} total")
    for status in Status:
        n = counts[status]
        if n:
            print(f"  {status.value}: {n}")

    pending = InboxSource(root / ".hornero").poll()
    print(f"inbox: {len(pending)} pending signal(s)")

    from hornero.memory.reindex import index_staleness

    print(f"knowledge index: {index_staleness(root)}")
    return 0


def _stub(phase: str) -> int:
    print(f"not implemented yet (arrives in phase {phase})", file=sys.stderr)
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hornero")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("new", help="create a repository from a versioned blueprint")
    p.add_argument("name")
    p.add_argument("--path", default=None, help="destination (default: ./NAME)")
    p.add_argument("--blueprint", default="python-service")
    p.add_argument("--component", action="append", default=[])
    p.add_argument("--capability", action="append", default=[])
    p.add_argument("--registry", default=None)
    p.add_argument("--registry-key-env", default="HORNERO_REGISTRY_KEY")
    p.add_argument("--var", action="append", default=[], metavar="KEY=VALUE")
    p.add_argument("--no-git", action="store_true")
    p.add_argument("--commit", action="store_true")
    p = sub.add_parser("init", help="scaffold .hornero/ + the sdd/ layout")
    p.add_argument("--hooks", action="store_true",
                   help="also install the post-merge reindex git hook (opt-in)")
    p.add_argument("--print-ci-hook", action="store_true",
                   help="print a CI reindex snippet and exit (writes nothing)")
    p.add_argument("--no-sdd", action="store_true",
                   help="skip the SDD toolkit install step")
    p.add_argument("--no-wiki", action="store_true",
                   help="skip the wiki-init offer")
    sub.add_parser("status", help="spec counts, inbox, index health")
    p_blueprint = sub.add_parser("blueprint", help="blueprint inventory and drift")
    blueprint_sub = p_blueprint.add_subparsers(dest="blueprint_command", required=True)
    blueprint_sub.add_parser("list", help="list built-in blueprints")
    pb = blueprint_sub.add_parser("status", help="show blueprint version and file drift")
    pb.add_argument("--json", action="store_true", dest="as_json")
    pb = blueprint_sub.add_parser("resolve", help="resolve stack capabilities")
    pb.add_argument("capabilities", nargs="+")
    pb.add_argument("--component", action="append", default=[])
    pb.add_argument("--registry", default=None)
    pb.add_argument("--registry-key-env", default="HORNERO_REGISTRY_KEY")
    pb = blueprint_sub.add_parser("upgrade", help="three-way blueprint upgrade")
    pb.add_argument("--registry", default=None)
    pb.add_argument("--registry-key-env", default="HORNERO_REGISTRY_KEY")
    pb.add_argument("--theirs", action="append", default=[])
    pb.add_argument("--ours", action="append", default=[])
    pb.add_argument("--dry-run", action="store_true")
    pb.add_argument("--json", action="store_true", dest="as_json")
    p_validate = sub.add_parser("validate", help="validate graph and traceability")
    p_validate.add_argument("--repair", action="store_true")
    p_validate.add_argument("--json", action="store_true", dest="as_json")
    p_ingest = sub.add_parser("ingest", help="normalize documents into the inbox")
    p_ingest.add_argument("files", nargs="+")
    p_ingest.add_argument("--kind", default="document")
    p_extract = sub.add_parser(
        "extract", help="propose graph knowledge from a document"
    )
    p_extract.add_argument("file")
    p_extract.add_argument("--no-write", action="store_true")
    p_contracts = sub.add_parser("contracts", help="generate API/event/data contracts")
    contracts_sub = p_contracts.add_subparsers(dest="contracts_command", required=True)
    contracts_sub.add_parser("generate", help="write generated contracts")
    contracts_sub.add_parser("check", help="check generated contract drift")
    p_workspace = sub.add_parser("workspace", help="federate Hornero repositories")
    workspace_sub = p_workspace.add_subparsers(dest="workspace_command", required=True)
    pw = workspace_sub.add_parser("graph", help="build a federated workspace graph")
    pw.add_argument("path")
    pw.add_argument("--json", action="store_true", dest="as_json")
    pw = workspace_sub.add_parser("plan", help="plan cross-repository impact")
    pw.add_argument("path")
    pw.add_argument("target")
    pw.add_argument("--json", action="store_true", dest="as_json")
    p_improve = sub.add_parser("improve", help="continuous-improvement loop")
    improve_sub = p_improve.add_subparsers(dest="improve_command", required=True)
    pi = improve_sub.add_parser("scan", help="validate and detect findings")
    pi.add_argument("--pack", action="append", default=[])
    pi = improve_sub.add_parser("plan", help="prioritize open findings")
    pi.add_argument("--limit", type=int, default=20)
    pi = improve_sub.add_parser("run", help="execute policy-approved plan items")
    pi.add_argument("--approve", action="append", default=[], metavar="FIND-ID")
    pi = improve_sub.add_parser("status", help="show finding and execution status")
    pi.add_argument("--json", action="store_true", dest="as_json")
    pi = improve_sub.add_parser("baseline", help="suppress or accept one finding")
    pi.add_argument("finding_id")
    pi.add_argument("--status", choices=["suppressed", "accepted_risk"], required=True)
    pi.add_argument("--reason", required=True)
    pi.add_argument("--owner", required=True)
    pi.add_argument("--expires", required=True)
    pi = improve_sub.add_parser("baseline-status", help="show baseline entries")
    pi.add_argument("--json", action="store_true", dest="as_json")
    p_assurance = sub.add_parser("assurance", help="security and compliance evidence")
    assurance_sub = p_assurance.add_subparsers(dest="assurance_command", required=True)
    pa = assurance_sub.add_parser("supply-chain", help="generate SBOM and dependency findings")
    pa.add_argument("--feed", default=None)
    assurance_sub.add_parser("threat-model", help="derive a STRIDE threat model")
    pa = assurance_sub.add_parser("compliance", help="map controls to evidence")
    pa.add_argument("framework", choices=["soc2", "iso27001", "gdpr", "pci"])
    p_runtime = sub.add_parser("runtime", help="persistent autonomous event runtime")
    runtime_sub = p_runtime.add_subparsers(dest="runtime_command", required=True)
    pr = runtime_sub.add_parser("init", help="write default-off runtime settings")
    pr.add_argument("--enable", action="store_true")
    pr = runtime_sub.add_parser("emit", help="enqueue a runtime action")
    pr.add_argument("action", choices=[
        "scan", "plan", "run", "validate", "supply_chain", "threat_model",
        "compliance",
    ])
    pr.add_argument("--data", default="{}", help="JSON object payload")
    pr.add_argument("--risk", choices=["low", "medium", "high"], default="low")
    pr.add_argument("--cost", type=int, default=1)
    pr = runtime_sub.add_parser("tick", help="process due events within budgets")
    pr.add_argument("--now", type=float, default=None)
    pr = runtime_sub.add_parser("webhook", help="ingest a signed event envelope")
    pr.add_argument("file")
    pr.add_argument("--signature", required=True)
    pr.add_argument("--key-env", default="HORNERO_WEBHOOK_KEY")
    pr = runtime_sub.add_parser("approve", help="approve a queued risky event")
    pr.add_argument("event_id")
    pr.add_argument("--by", required=True)
    pr = runtime_sub.add_parser("feedback", help="record finding outcome feedback")
    pr.add_argument("finding_id")
    feedback_group = pr.add_mutually_exclusive_group(required=True)
    feedback_group.add_argument("--helpful", action="store_true")
    feedback_group.add_argument("--not-helpful", action="store_true")
    pr.add_argument("--notes", default="")
    pr = runtime_sub.add_parser("status", help="show events, metrics and policy weights")
    pr.add_argument("--json", action="store_true", dest="as_json")
    p = sub.add_parser("reconcile", help="poll -> deltas -> HITL -> apply")
    p.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("build", help="approved specs -> briefs -> dispatch")
    p.add_argument("spec_ids", nargs="*")
    p.add_argument("--backend", choices=["cli", "mock"])
    sub.add_parser("reindex", help="rebuild .hornero/knowledge/")
    p = sub.add_parser("report", help="regenerate sdd/reports/*.html")
    p.add_argument("--only")
    p_runs = sub.add_parser("runs", help="flight-recorder traces (SPEC-004)")
    runs_sub = p_runs.add_subparsers(dest="runs_command", required=True)
    pr = runs_sub.add_parser("list", help="registered agent runs")
    pr.add_argument("--spec", default=None)
    pr = runs_sub.add_parser("show", help="events of one run")
    pr.add_argument("run_ref")
    pr.add_argument("--kind", default=None, help="comma-separated kind filter")
    pr.add_argument("--range", dest="span", default=None, metavar="e#N:e#M")
    pr = runs_sub.add_parser("adopt", help="adopt a Claude Code transcript")
    pr.add_argument("transcript")
    pr = runs_sub.add_parser("prune", help="delete old trace directories")
    pr.add_argument("--keep-days", type=float, required=True)
    p_scribe = sub.add_parser("scribe", help="distill a trace into a DR (SPEC-004)")
    p_scribe.add_argument("run_ref")
    p_scribe.add_argument("--force", action="store_true",
                          help="re-scribe a run that already has a DR")
    p_wiki = sub.add_parser("wiki", help="agent-facing living wiki (SPEC-003)")
    wiki_sub = p_wiki.add_subparsers(dest="wiki_command", required=True)
    wiki_sub.add_parser("init", help="first full wiki build")
    wiki_sub.add_parser("update", help="surgical refresh scoped by the watermark")
    p_parrot = wiki_sub.add_parser(
        "parrot", help="ai-parrot LLM-wiki retrieval plane"
    )
    parrot_sub = p_parrot.add_subparsers(dest="parrot_command", required=True)
    pp = parrot_sub.add_parser("build", help="build or refresh the plane")
    pp.add_argument("--force", action="store_true")
    pp.add_argument("--no-git", action="store_true")
    pp.add_argument("--no-export", action="store_true")
    pp.add_argument("--no-graph", action="store_true")
    pp.add_argument("--quiet", "-q", action="store_true")
    pp = parrot_sub.add_parser("upsert", help="incrementally refresh files")
    pp.add_argument("paths", nargs="*")
    pp.add_argument("--changed", action="store_true")
    pp.add_argument("--quiet", "-q", action="store_true")
    pp = parrot_sub.add_parser("query", help="query ranked wiki pages")
    pp.add_argument("question")
    pp.add_argument("--top-k", type=int, default=12)
    pp.add_argument("--budget", type=int, default=2400)
    pp.add_argument("--category", default=None)
    pp.add_argument("--json", action="store_true", dest="as_json")
    pp = parrot_sub.add_parser("page", help="read one full page")
    pp.add_argument("page_id")
    pp.add_argument("--max-tokens", type=int, default=None)
    pp.add_argument("--json", action="store_true", dest="as_json")
    pp = parrot_sub.add_parser("related", help="follow typed page edges")
    pp.add_argument("page_id")
    pp.add_argument("--rel", default=None)
    pp.add_argument("--direction", choices=["out", "in", "both"], default="both")
    pp.add_argument("--json", action="store_true", dest="as_json")
    pp = parrot_sub.add_parser("status", help="show plane health and staleness")
    pp.add_argument("--json", action="store_true", dest="as_json")
    pp = parrot_sub.add_parser("export", help="export a human-readable wiki")
    pp.add_argument("--output", "-o", default="docs/wiki")

    p_codex = wiki_sub.add_parser(
        "codex", help="install ai-parrot guidance and hooks for Codex"
    )
    codex_sub = p_codex.add_subparsers(dest="codex_command", required=True)
    pc = codex_sub.add_parser("install", help="install the Codex integration")
    pc.add_argument("--no-git-hook", action="store_true")
    pc.add_argument("--no-gitignore", action="store_true")
    codex_sub.add_parser("uninstall", help="remove managed Codex artifacts")
    pc = codex_sub.add_parser("status", help="show Codex integration state")
    pc.add_argument("--json", action="store_true", dest="as_json")
    codex_sub.add_parser("hook", help=argparse.SUPPRESS)

    p_knowledge = sub.add_parser("knowledge", help="local code knowledge graph")
    knowledge_sub = p_knowledge.add_subparsers(dest="knowledge_command", required=True)
    pk = knowledge_sub.add_parser("query", help="query the local knowledge graph")
    pk.add_argument("question")
    pk.add_argument("--top-k", type=int, default=8)
    pk.add_argument("--budget", type=int, default=1200)
    pk.add_argument("--category", default=None)
    pk.add_argument("--json", action="store_true", dest="as_json")
    pk = knowledge_sub.add_parser("history", help="show temporal entity versions")
    pk.add_argument("entity_id")
    pk.add_argument("--json", action="store_true", dest="as_json")
    pk = knowledge_sub.add_parser("analyze", help="detect graph contradictions or duplicates")
    pk.add_argument("kind", choices=["contradictions", "duplicates"])
    pk.add_argument("--json", action="store_true", dest="as_json")
    pk = knowledge_sub.add_parser("impact", help="show bounded semantic impact")
    pk.add_argument("entity_id")
    pk.add_argument("--depth", type=int, default=4)
    pk.add_argument("--max-nodes", type=int, default=100)
    pk.add_argument("--json", action="store_true", dest="as_json")
    pk = knowledge_sub.add_parser("coverage", help="score requirement traceability")
    pk.add_argument("--json", action="store_true", dest="as_json")
    pk = knowledge_sub.add_parser("semantic-query", help="filter semantic entities")
    pk.add_argument("--kind")
    pk.add_argument("--text", default="")
    pk.add_argument("--limit", type=int, default=20)
    pk.add_argument("--json", action="store_true", dest="as_json")
    pk = knowledge_sub.add_parser("explain", help="explain an entity from evidence and impact")
    pk.add_argument("entity_id")
    pk.add_argument("--json", action="store_true", dest="as_json")
    pk = knowledge_sub.add_parser("context", help="build a bounded agent context pack")
    pk.add_argument("entity_id")
    pk.add_argument("--budget", type=int, default=1200)
    pk.add_argument("--json", action="store_true", dest="as_json")
    pk = knowledge_sub.add_parser("page", help="read one graph page")
    pk.add_argument("page_id")
    pk.add_argument("--max-chars", type=int, default=None)
    pk.add_argument("--json", action="store_true", dest="as_json")
    pk = knowledge_sub.add_parser("related", help="follow graph edges")
    pk.add_argument("page_id")
    pk.add_argument("--rel", default=None)
    pk.add_argument("--direction", choices=["out", "in", "both"], default="both")
    pk.add_argument("--json", action="store_true", dest="as_json")
    pk = knowledge_sub.add_parser("status", help="graph stats and report path")
    pk.add_argument("--json", action="store_true", dest="as_json")
    pk = knowledge_sub.add_parser("entity", help="read a semantic entity")
    pk.add_argument("entity_id")
    pk.add_argument("--json", action="store_true", dest="as_json")
    pk = knowledge_sub.add_parser("relations", help="follow semantic relations")
    pk.add_argument("entity_id")
    pk.add_argument("--rel", default=None)
    pk.add_argument("--direction", choices=["out", "in", "both"], default="both")
    pk.add_argument("--json", action="store_true", dest="as_json")

    p_sdd = sub.add_parser("sdd", help="SDD toolkit management (SPEC-002)")
    sdd_sub = p_sdd.add_subparsers(dest="sdd_command", required=True)
    pi = sdd_sub.add_parser("install", help="install toolkit + scaffold + lockfile")
    pi.add_argument("--from", dest="source", help="git URL or local path")
    pi.add_argument("--ref", default=None)
    pi.add_argument("--force", action="store_true",
                    help="overwrite locally modified managed files")
    ps = sdd_sub.add_parser("status", help="drift table, one line per managed file")
    ps.add_argument("--from", dest="source", default=None)
    ps.add_argument("--ref", default=None)
    pd = sdd_sub.add_parser("diff", help="upstream vs local unified diff")
    pd.add_argument("file", nargs="?", default=None)
    pd.add_argument("--from", dest="source", default=None)
    pd.add_argument("--ref", default=None)
    py = sdd_sub.add_parser("sync", help="pull toolkit updates (pull is the default)")
    py.add_argument("--pull", action="store_true",
                    help="pull direction (the default; flag kept for symmetry)")
    py.add_argument("--push", nargs="*", default=None, metavar="FILE",
                    help="promote modified files upstream via a PR")
    py.add_argument("--workspace", default=None, metavar="DIR",
                    help="pull-sync every child repo carrying .hornero/sdd.lock")
    py.add_argument("--dry-run", action="store_true")
    py.add_argument("--theirs", action="append", default=[], metavar="FILE",
                    help="resolve a diverged file by copying upstream")
    py.add_argument("--ours", action="append", default=[], metavar="FILE",
                    help="resolve a diverged file by keeping local (re-baseline)")
    py.add_argument("--force", action="store_true")
    py.add_argument("--allow-secrets", action="store_true",
                    help="override the push secret scan for this run")
    py.add_argument("--from", dest="source", default=None)
    py.add_argument("--ref", default=None)
    for name, help_text in (
        ("hold", "set policy=local (never pulled)"),
        ("unhold", "set policy=sync"),
        ("pin", "set policy=pinned (frozen at current version)"),
    ):
        pp = sdd_sub.add_parser(name, help=help_text)
        pp.add_argument("file")
    return parser


def _cmd_knowledge(args: argparse.Namespace, root: Path) -> int:
    import json

    from hornero.memory import codegraph, intelligence

    if args.knowledge_command == "query":
        hits = codegraph.search(
            root, args.question, limit=args.top_k, category=args.category
        )
        if args.as_json:
            print(json.dumps([h.__dict__ for h in hits], indent=2, ensure_ascii=False))
            return 0
        if not hits:
            print(
                f"no graph results for {args.question!r}; run 'hornero reindex' "
                "or fall back to code search"
            )
            return 0
        packed, used, total = codegraph.pack_hits(hits, budget_tokens=args.budget)
        print(f"# Knowledge graph results for: {args.question}\n")
        print(packed)
        print(
            f"\n({len(packed.splitlines())}/{total} results, ~{used} tokens)"
        )
        print(
            "Next: 'hornero knowledge page <id>' for a full page; "
            "'hornero knowledge related <id>' for linked pages."
        )
        return 0
    if args.knowledge_command == "history":
        rows = intelligence.history(root, args.entity_id)
        if args.as_json:
            print(json.dumps(rows, indent=2, ensure_ascii=False))
        else:
            for row in rows:
                state = "active" if row["active"] else "superseded"
                print(
                    f"{row['first_snapshot']}..{row['last_snapshot']} "
                    f"{state} {row['version_hash'][:12]}"
                )
        return 0 if rows else 2
    if args.knowledge_command == "analyze":
        analysis_rows = (
            intelligence.contradictions(root)
            if args.kind == "contradictions"
            else intelligence.duplicates(root)
        )
        payload = [row.__dict__ for row in analysis_rows]
        if args.as_json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            for analysis_item in analysis_rows:
                print(
                    f"{analysis_item.analysis_id} {analysis_item.score:.2f} "
                    f"{analysis_item.left} <-> {analysis_item.right}: "
                    f"{analysis_item.evidence}"
                )
        return 0
    if args.knowledge_command == "impact":
        try:
            result = intelligence.impact(
                root, args.entity_id, max_depth=args.depth,
                max_nodes=args.max_nodes,
            )
        except (KeyError, ValueError) as exc:
            print(f"impact failed: {exc}", file=sys.stderr)
            return 2
        if args.as_json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"impact: {result['nodes']} node(s)")
            for item in result["paths"]:
                print(
                    f"depth={item['depth']} [{item.get('kind', '?')}] "
                    f"{item['entity_id']} via {item['via']}"
                )
        return 0
    if args.knowledge_command == "coverage":
        rows = intelligence.coverage(root)
        if args.as_json:
            print(json.dumps(rows, indent=2, ensure_ascii=False))
        else:
            for row in rows:
                missing = ",".join(row["missing"]) or "-"
                print(f"{row['score']:>5.1f}% {row['entity_id']} missing={missing}")
        return 0
    if args.knowledge_command == "semantic-query":
        rows = intelligence.semantic_query(
            root, kind=args.kind, text=args.text, limit=args.limit
        )
        if args.as_json:
            print(json.dumps(rows, indent=2, ensure_ascii=False))
        else:
            for row in rows:
                print(f"[{row['kind']}] {row['entity_id']} - {row['title']}")
        return 0
    if args.knowledge_command in ("explain", "context"):
        try:
            result = (
                intelligence.explain(root, args.entity_id)
                if args.knowledge_command == "explain"
                else intelligence.context_pack(
                    root, args.entity_id, budget_tokens=args.budget
                )
            )
        except (KeyError, ValueError) as exc:
            print(f"knowledge {args.knowledge_command} failed: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    if args.knowledge_command == "page":
        page = codegraph.get_page(root, args.page_id)
        if page is None:
            print(f"page not found: {args.page_id}", file=sys.stderr)
            return 2
        if args.as_json:
            print(json.dumps(page.__dict__, indent=2, ensure_ascii=False))
            return 0
        body = page.body
        if args.max_chars is not None and len(body) > args.max_chars:
            body = body[:args.max_chars].rstrip() + "\n\n[... truncated]"
        print(f"# {page.title}  [{page.concept_id}]")
        print(f"category: {page.category}")
        if page.summary:
            print(f"summary: {page.summary}\n")
        print(body)
        return 0
    if args.knowledge_command == "related":
        rows = codegraph.related(
            root, args.page_id, rel=args.rel, direction=args.direction
        )
        if args.as_json:
            print(json.dumps(rows, indent=2, ensure_ascii=False))
            return 0
        if not rows:
            print(f"no related pages for {args.page_id!r}")
            return 0
        for row in rows:
            arrow = "->" if row["direction"] == "out" else "<-"
            print(
                f"{arrow} [{row['concept_id']}] ({row['rel']}) "
                f"{row['title']} — {row['summary']}"
            )
        return 0
    if args.knowledge_command == "status":
        st = codegraph.stats(root)
        st["html_report"] = str(codegraph.html_report_path(root))
        if args.as_json:
            print(json.dumps(st, indent=2, ensure_ascii=False))
            return 0
        if not st.get("built"):
            print("knowledge graph: absent (run 'hornero reindex')")
            return 0
        print(f"knowledge graph: {st['pages']} pages, {st['edges']} edges")
        print(
            f"semantic: {st['semantic_entities']} entities, "
            f"{st['semantic_relations']} relations, "
            f"{st['provenance']} provenance records"
        )
        print(f"sources: {st['sources']}; fts5: {'yes' if st['fts'] else 'no'}")
        print(f"categories: {st['categories']}")
        print(f"html report: {st['html_report']}")
        return 0
    if args.knowledge_command == "entity":
        entity = codegraph.get_entity(root, args.entity_id)
        if entity is None:
            print(f"entity not found: {args.entity_id}", file=sys.stderr)
            return 2
        if args.as_json:
            print(json.dumps(entity, indent=2, ensure_ascii=False))
        else:
            print(f"[{entity['kind']}] {entity['entity_id']} - {entity['title']}")
            print(entity["summary"])
            provenance = entity["provenance"]
            assert isinstance(provenance, list)
            for item in provenance:
                print(f"source: {item['source_path']} ({item['origin']})")
        return 0
    if args.knowledge_command == "relations":
        semantic_rows = codegraph.semantic_related(
            root, args.entity_id, rel=args.rel, direction=args.direction
        )
        if args.as_json:
            print(json.dumps(semantic_rows, indent=2, ensure_ascii=False))
        else:
            for semantic_row in semantic_rows:
                arrow = "->" if semantic_row["direction"] == "out" else "<-"
                print(
                    f"{arrow} [{semantic_row['entity_id']}] "
                    f"({semantic_row['rel']}) {semantic_row['title']}"
                )
        return 0
    raise AssertionError("unreachable")


def _cmd_parrot_wiki(args: argparse.Namespace, root: Path) -> int:
    """Translate stable Hornero argv to ai-parrot's wikitoolkit CLI."""
    from hornero.parrot_wiki import ParrotWikiError, run_toolkit

    command = args.parrot_command
    forwarded: list[str] = [command]
    if command == "build":
        if args.force:
            forwarded.append("--force")
        if args.no_git:
            forwarded.append("--no-git")
        if args.no_export:
            forwarded.append("--no-export")
        if args.no_graph:
            forwarded.append("--no-graph")
        if args.quiet:
            forwarded.append("--quiet")
    elif command == "upsert":
        forwarded.extend(args.paths)
        if args.changed:
            forwarded.append("--changed")
        if args.quiet:
            forwarded.append("--quiet")
    elif command == "query":
        forwarded.extend(
            ["--top-k", str(args.top_k), "--budget", str(args.budget)]
        )
        if args.category:
            forwarded.extend(["--category", args.category])
        if args.as_json:
            forwarded.append("--json")
        forwarded.extend(["--", args.question])
    elif command == "page":
        if args.max_tokens is not None:
            forwarded.extend(["--max-tokens", str(args.max_tokens)])
        if args.as_json:
            forwarded.append("--json")
        forwarded.extend(["--", args.page_id])
    elif command == "related":
        forwarded.extend(["--direction", args.direction])
        if args.rel:
            forwarded.extend(["--rel", args.rel])
        if args.as_json:
            forwarded.append("--json")
        forwarded.extend(["--", args.page_id])
    elif command == "status" and args.as_json:
        forwarded.append("--json")
    elif command == "export":
        forwarded.extend(["--output", args.output])
    try:
        return run_toolkit(root, forwarded)
    except ParrotWikiError as exc:
        print(f"parrot wiki failed: {exc}", file=sys.stderr)
        return 2


def _cmd_codex_wiki(args: argparse.Namespace, root: Path) -> int:
    from hornero.parrot_wiki import (
        ParrotWikiError,
        install_codex_integration,
        integration_status,
        run_codex_hook,
        uninstall_codex_integration,
    )

    if args.codex_command == "hook":
        return run_codex_hook()
    try:
        if args.codex_command == "install":
            actions = install_codex_integration(
                root,
                git_hook=not args.no_git_hook,
                gitignore=not args.no_gitignore,
            )
            for action in actions:
                print(action)
            print(
                "Codex project hooks require a trusted repository; review/enable "
                "them with /hooks in Codex."
            )
            return 0
        if args.codex_command == "uninstall":
            for action in uninstall_codex_integration(root):
                print(action)
            return 0
        status = integration_status(root)
        if args.as_json:
            print(json.dumps(status, indent=2, sort_keys=True))
        else:
            for key, value in status.items():
                print(f"{key.replace('_', ' '):<24} {'yes' if value else 'no'}")
        return 0
    except ParrotWikiError as exc:
        print(f"codex wiki integration failed: {exc}", file=sys.stderr)
        return 2


def _cmd_sdd(args: argparse.Namespace, root: Path) -> int:
    from datetime import datetime, timezone

    from hornero.config import ConfigError, load_config
    from hornero.sdd_toolkit.cli_sync import SyncError, cmd_policy
    from hornero.sdd_toolkit.manifest import ManifestError
    from hornero.sdd_toolkit.upstream import UpstreamError

    if args.sdd_command in ("hold", "unhold", "pin"):  # no upstream needed
        try:
            return cmd_policy(root, args.file, args.sdd_command)
        except SyncError as exc:
            print(f"sdd {args.sdd_command} failed: {exc}", file=sys.stderr)
            return 2

    if args.sdd_command == "sync" and args.workspace is not None:
        # fanout: each child's lock is its own sync identity — no cwd
        # upstream needed.
        from hornero.sdd_toolkit.push import cmd_workspace

        try:
            return cmd_workspace(
                Path(args.workspace),
                synced_at=datetime.now(timezone.utc).isoformat(),
                force=args.force,
            )
        except SyncError as exc:
            print(f"sdd sync failed: {exc}", file=sys.stderr)
            return 2

    try:
        cfg = load_config(root)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 1
    from hornero.sdd_toolkit.lock import load_lock

    lock = load_lock(root)
    # --from wins; then the lock (the repo's sync identity); then config.
    source = args.source or (lock.upstream if lock else "") or cfg.sdd_upstream
    if not source:
        print(
            "no toolkit upstream configured: pass --from <git-url|path> or set "
            "'sdd_upstream:' in .hornero/config.yaml",
            file=sys.stderr,
        )
        return 2
    ref = args.ref or (lock.upstream_ref if lock and not args.source else "") \
        or cfg.sdd_ref
    now = datetime.now(timezone.utc).isoformat()

    try:
        if args.sdd_command == "install":
            from hornero.sdd_toolkit.install import install

            return install(root, source, ref, force=args.force, synced_at=now)

        from hornero.sdd_toolkit import cli_sync

        if args.sdd_command == "status":
            return cli_sync.cmd_status(root, source, ref)
        if args.sdd_command == "diff":
            return cli_sync.cmd_diff(root, source, ref, args.file)
        if args.sdd_command == "sync":
            if args.push is not None:
                from hornero.sdd_toolkit import push as push_mod

                return push_mod.push(
                    root, args.push, source=source, ref=ref,
                    runner=push_mod.subprocess_runner,
                    allow_secrets=args.allow_secrets,
                )
            return cli_sync.cmd_sync(
                root, source, ref, dry_run=args.dry_run, theirs=args.theirs,
                ours=args.ours, force=args.force, synced_at=now,
            )
    except SyncError as exc:
        print(f"sdd {args.sdd_command} failed: {exc}", file=sys.stderr)
        return 2
    except (UpstreamError, ManifestError) as exc:
        print(f"sdd {args.sdd_command} failed: {exc}", file=sys.stderr)
        return 1
    raise AssertionError("unreachable")


def _cmd_runs(args: argparse.Namespace, root: Path) -> int:
    import shutil
    import time

    from hornero import flight

    if args.runs_command == "list":
        with Ledger(root / ".hornero" / "ledger.db") as led:
            rows = led.agent_runs(spec_id=args.spec)
        for r in rows:
            print(f"{r['run_ref']}  {r['status']:<12} "
                  f"{r['spec_id'] or '-':<10} {r['actor']}")
        print(f"{len(rows)} run(s)")
        return 0
    if args.runs_command == "show":
        try:
            events = flight.read_trace(root, args.run_ref)
        except FileNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        kinds = set(args.kind.split(",")) if args.kind else None
        try:
            span = flight.parse_range(args.span) if args.span else None
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        for e in flight.slice_events(events, kinds, span):
            print(f"e#{e['seq']:<5} {e['kind']:<16} {e['summary']}")
        return 0
    if args.runs_command == "adopt":
        transcript = Path(args.transcript)
        if not transcript.is_file():
            print(f"no such transcript: {transcript}", file=sys.stderr)
            return 2
        run_ref = flight.adopt_transcript(root, transcript)
        events = flight.read_trace(root, run_ref)
        with Ledger(root / ".hornero" / "ledger.db") as led:
            led.record_agent_run(
                run_ref, spec_id=None, task_id=None, actor="adopted:claude-code",
                status="adopted", trace_path=str(flight.runs_dir(root) / run_ref),
                started_at=events[0]["ts"], finished_at=events[-1]["ts"],
            )
        print(f"adopted as {run_ref} ({len(events)} event(s))")
        return 0
    if args.runs_command == "prune":
        cutoff = time.time() - args.keep_days * 86400
        removed = 0
        with Ledger(root / ".hornero" / "ledger.db") as led:
            for r in led.agent_runs():
                finished = r["finished_at"] or r["started_at"]
                run_dir = flight.runs_dir(root) / r["run_ref"]
                if finished < cutoff and run_dir.is_dir():
                    shutil.rmtree(run_dir)  # ledger row stays: audit history
                    removed += 1
        print(f"pruned {removed} trace dir(s)")
        return 0
    raise AssertionError("unreachable")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    from hornero.project import ProjectRootError, discover_root, init_root

    try:
        bootstrap_sdd = args.command == "sdd" and (
            args.sdd_command == "install"
            or (args.sdd_command == "sync" and args.workspace is not None)
        )
        global_blueprint = (
            args.command == "blueprint"
            and args.blueprint_command in ("list", "resolve")
        )
        global_workspace = args.command == "workspace"
        root = (
            init_root(Path.cwd())
            if args.command in ("init", "new") or bootstrap_sdd
            or global_blueprint or global_workspace
            else discover_root(Path.cwd())
        )
    except ProjectRootError as exc:
        print(f"project error: {exc}", file=sys.stderr)
        return 2
    if args.command == "new":
        from hornero.blueprint_registry import load_registry, merge_registry
        from hornero.blueprints import (
            BLUEPRINTS,
            COMPONENTS,
            BlueprintError,
            create_project,
            resolve_capabilities,
        )

        variables: dict[str, str] = {}
        for item in args.var:
            if "=" not in item:
                print(f"invalid --var {item!r}; expected KEY=VALUE", file=sys.stderr)
                return 2
            key, value = item.split("=", 1)
            if not key or key in variables:
                print(f"invalid or duplicate --var key: {key!r}", file=sys.stderr)
                return 2
            variables[key] = value
        destination = Path(args.path) if args.path else Path.cwd() / args.name
        if not destination.is_absolute():
            destination = Path.cwd() / destination
        try:
            component_catalog = COMPONENTS
            blueprint_catalog = BLUEPRINTS
            registry_identity = None
            if args.registry:
                registry = load_registry(
                    args.registry, key_env=args.registry_key_env
                )
                component_catalog, blueprint_catalog = merge_registry(registry)
                registry_identity = registry.identity
            blueprint = blueprint_catalog.get(args.blueprint)
            if blueprint is None:
                raise BlueprintError(f"unknown blueprint {args.blueprint!r}")
            selected = resolve_capabilities(
                args.capability,
                [*blueprint.components, *args.component],
                component_catalog=component_catalog,
            )
            extras = [item for item in selected if item not in blueprint.components]
            created = create_project(
                destination, args.name, blueprint_name=args.blueprint,
                supplied_variables=variables, extra_components=extras,
                git=not args.no_git, commit=args.commit,
                initializer=lambda target: _cmd_init(
                    target, no_sdd=True, no_wiki=True
                ),
                component_catalog=component_catalog,
                blueprint_catalog=blueprint_catalog,
                registry=registry_identity,
            )
        except BlueprintError as exc:
            print(f"new failed: {exc}", file=sys.stderr)
            return 1
        print(f"created {args.blueprint} project at {created}")
        return 0
    if args.command == "init":
        if args.print_ci_hook:
            from hornero.hooks import CI_SNIPPET

            print(CI_SNIPPET, end="")
            return 0
        rc = _cmd_init(root, no_sdd=args.no_sdd, no_wiki=args.no_wiki)
        if rc == 0 and args.hooks:
            from hornero.hooks import HookError, install_post_merge_hook

            try:
                print(install_post_merge_hook(root))
            except HookError as exc:
                print(f"hook install failed: {exc}", file=sys.stderr)
                return 1
        return rc
    if args.command == "status":
        return _cmd_status(root)
    if args.command == "validate":
        from hornero.memory.validate import validate

        report = validate(root, repair=args.repair)
        if args.as_json:
            print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
        else:
            print(
                f"validation: {report.state}; {len(report.findings)} finding(s), "
                f"{report.blocking} blocking"
            )
            for finding in report.findings:
                print(
                    f"{finding.severity:<8} {finding.finding_id} "
                    f"{finding.code}: {finding.message} [{finding.subject}]"
                )
        return 1 if report.blocking else 0
    if args.command == "ingest":
        from hornero.ingest import IngestError, ingest

        failures = 0
        for item in args.files:
            try:
                output = ingest(root, Path(item), kind=args.kind)
                print(f"ingested: {item} -> {output.relative_to(root)}")
            except IngestError as exc:
                failures += 1
                print(f"ingest failed: {exc}", file=sys.stderr)
        return 1 if failures else 0
    if args.command == "extract":
        from hornero.llm import LLMError, resolve_llm
        from hornero.memory.intelligence import extract_proposals

        source = Path(args.file)
        if not source.is_file():
            print(f"extract failed: no such file: {source}", file=sys.stderr)
            return 2
        try:
            cfg = load_config(root)
            llm = resolve_llm(cfg, root, "extractor")
            if llm is None:
                print(
                    "no model configured for extractor (set models.extractor)",
                    file=sys.stderr,
                )
                return 3
            result = extract_proposals(
                root, source, llm, persist=not args.no_write
            )
        except (ConfigError, LLMError, OSError, ValueError) as exc:
            print(f"extract failed: {exc}", file=sys.stderr)
            return 1
        print(
            f"extraction: {len(result['accepted'])} accepted proposal(s), "
            f"{result['rejected']} rejected"
        )
        return 0
    if args.command == "contracts":
        from hornero.contracts import ContractError, generate

        try:
            result = generate(root, check=args.contracts_command == "check")
        except ContractError as exc:
            print(f"contracts failed: {exc}", file=sys.stderr)
            return 2
        contract_files = result["files"]
        assert isinstance(contract_files, dict)
        for rel, state in contract_files.items():
            print(f"{state:<8} {rel}")
        return 0 if args.contracts_command == "generate" or result["current"] else 1
    if args.command == "runtime":
        from hornero.runtime import (
            RuntimeError,
            approve,
            emit,
            feedback,
            ingest_webhook,
            status,
            tick,
            write_default,
        )

        try:
            if args.runtime_command == "init":
                print(write_default(root, enabled=args.enable).relative_to(root))
                return 0
            if args.runtime_command == "emit":
                payload = json.loads(args.data)
                if not isinstance(payload, dict):
                    raise RuntimeError("runtime event data must be a JSON object")
                print(emit(
                    root, args.action, payload=payload, risk=args.risk,
                    cost_units=args.cost,
                ))
                return 0
            if args.runtime_command == "tick":
                result = tick(root, now=args.now)
                print(json.dumps(result, indent=2, sort_keys=True))
                return 0
            if args.runtime_command == "webhook":
                event_id, webhook_created = ingest_webhook(
                    root, Path(args.file).read_bytes(), signature=args.signature,
                    key_env=args.key_env,
                )
                print(
                    f"{event_id} "
                    f"({'created' if webhook_created else 'replay ignored'})"
                )
                return 0
            if args.runtime_command == "approve":
                approve(root, args.event_id, args.by)
                print(f"approved: {args.event_id} by {args.by}")
                return 0
            if args.runtime_command == "feedback":
                weight = feedback(
                    root, args.finding_id, helpful=args.helpful,
                    notes=args.notes,
                )
                print(f"feedback recorded; bounded rule weight={weight:.2f}")
                return 0
            result = status(root)
            if args.as_json:
                print(json.dumps(result, indent=2, sort_keys=True))
            else:
                metrics = result["metrics"]
                print(
                    f"runtime: {metrics['events']} events, "
                    f"cost={metrics['cost_units']}, attempts={metrics['attempts']}"
                )
                print(f"by status: {metrics['by_status']}")
            return 0
        except (RuntimeError, json.JSONDecodeError, ValueError) as exc:
            print(f"runtime {args.runtime_command} failed: {exc}", file=sys.stderr)
            return 2
    if args.command == "workspace":
        from hornero.workspace import WorkspaceError, build, plan

        try:
            result = (
                build(Path(args.path))
                if args.workspace_command == "graph"
                else plan(Path(args.path), args.target)
            )
        except (OSError, WorkspaceError) as exc:
            print(f"workspace {args.workspace_command} failed: {exc}", file=sys.stderr)
            return 2
        if args.as_json:
            print(json.dumps(result, indent=2, sort_keys=True))
        elif args.workspace_command == "graph":
            print(
                f"workspace: {len(result['repositories'])} repositories, "
                f"{len(result['nodes'])} nodes, {len(result['edges'])} edges"
            )
        else:
            print(
                f"workspace impact: {len(result['affected_nodes'])} nodes in "
                f"{', '.join(result['repositories'])}"
            )
        return 0
    if args.command == "improve":
        from hornero.improvement import controller
        from hornero.improvement.controller import ImprovementError
        from hornero.improvement.policy import PolicyError

        try:
            if args.improve_command == "baseline":
                from hornero.improvement.policy import set_baseline

                path = set_baseline(
                    root, args.finding_id, status=args.status,
                    reason=args.reason, owner=args.owner, expires=args.expires,
                )
                print(f"baseline updated: {path.relative_to(root)}")
                return 0
            if args.improve_command == "baseline-status":
                from hornero.improvement.policy import baseline_status

                entries = baseline_status(root)
                if args.as_json:
                    print(json.dumps(entries, indent=2, sort_keys=True))
                else:
                    for entry in entries:
                        state = "expired" if entry["expired"] else entry["status"]
                        print(
                            f"{entry['finding_id']} {state} owner={entry['owner']} "
                            f"expires={entry['expires']}"
                        )
                return 0
            if args.improve_command == "scan":
                findings = controller.scan(root, packs=args.pack or None)
                open_findings = [item for item in findings if item.status == "open"]
                print(
                    f"improvement scan: {len(open_findings)} open, "
                    f"{len(findings)} tracked"
                )
                for improvement_finding in open_findings:
                    print(
                        f"{improvement_finding.severity:<8} "
                        f"{improvement_finding.finding_id} "
                        f"[{improvement_finding.category}] "
                        f"{improvement_finding.title}"
                    )
                return 0
            if args.improve_command == "plan":
                plan_result = controller.plan(root, limit=args.limit)
                items = plan_result["items"]
                assert isinstance(items, list)
                print(f"improvement plan: {len(items)} item(s)")
                for item in items:
                    print(
                        f"{item['finding_id']} risk={item['risk']} "
                        f"{item['title']}"
                    )
                return 0
            if args.improve_command == "run":
                execution_results = controller.run(root, approved=set(args.approve))
                for execution_result in execution_results:
                    print(
                        f"{execution_result.status}: "
                        f"{execution_result.branch or '-'}: "
                        f"{execution_result.details}"
                    )
                return 0 if all(
                    execution_result.status == "ready_for_review"
                    for execution_result in execution_results
                ) else 1
            status_result = controller.status(root)
            if args.as_json:
                print(json.dumps(status_result, indent=2, sort_keys=True))
            else:
                print(
                    f"improvements: {status_result['findings']} findings, "
                    f"{status_result['plan_items']} planned item(s), "
                    f"{status_result['executions']} execution(s)"
                )
                print(f"by status: {status_result['by_status']}")
            return 0
        except (ImprovementError, PolicyError, ValueError, ConfigError) as exc:
            print(f"improve {args.improve_command} failed: {exc}", file=sys.stderr)
            return 1
    if args.command == "assurance":
        from hornero.assurance import (
            AssuranceError,
            compliance,
            supply_chain,
            threat_model,
        )

        try:
            if args.assurance_command == "supply-chain":
                result = supply_chain(
                    root, vulnerability_feed=Path(args.feed) if args.feed else None
                )
            elif args.assurance_command == "threat-model":
                result = threat_model(root)
            else:
                result = compliance(root, args.framework)
        except AssuranceError as exc:
            print(f"assurance failed: {exc}", file=sys.stderr)
            return 2
        print(
            f"assurance {args.assurance_command}: "
            f"{len(result.get('issues', []))} issue(s)"
        )
        return 0
    if args.command == "blueprint":
        from hornero.blueprint_registry import load_registry, merge_registry
        from hornero.blueprints import (
            BLUEPRINTS,
            COMPONENTS,
            BlueprintError,
            load_lock,
            resolve_capabilities,
            status,
            upgrade,
        )

        if args.blueprint_command == "list":
            for name, blueprint in sorted(BLUEPRINTS.items()):
                print(f"{name:<18} {blueprint.version:<8} {blueprint.description}")
            return 0
        if args.blueprint_command == "resolve":
            try:
                catalog = COMPONENTS
                if args.registry:
                    registry = load_registry(
                        args.registry, key_env=args.registry_key_env
                    )
                    catalog, _ = merge_registry(registry)
                resolved = resolve_capabilities(
                    args.capabilities, args.component,
                    component_catalog=catalog,
                )
            except BlueprintError as exc:
                print(f"blueprint resolve failed: {exc}", file=sys.stderr)
                return 2
            print("\n".join(resolved))
            return 0
        if args.blueprint_command == "upgrade":
            try:
                lock = load_lock(root)
                source = args.registry
                if source is None and isinstance(lock.get("registry"), dict):
                    source = lock["registry"].get("source")
                component_catalog = COMPONENTS
                blueprint_catalog = BLUEPRINTS
                identity = None
                if source:
                    registry = load_registry(
                        str(source), key_env=args.registry_key_env
                    )
                    component_catalog, blueprint_catalog = merge_registry(registry)
                    identity = registry.identity
                result = upgrade(
                    root, component_catalog=component_catalog,
                    blueprint_catalog=blueprint_catalog, registry=identity,
                    theirs=set(args.theirs), ours=set(args.ours),
                    dry_run=args.dry_run,
                )
            except BlueprintError as exc:
                print(f"blueprint upgrade failed: {exc}", file=sys.stderr)
                return 2
            if args.as_json:
                print(json.dumps(result, indent=2, sort_keys=True))
            else:
                print(
                    f"blueprint {result['blueprint']}: "
                    f"{result['from_version']} -> {result['to_version']}"
                )
                upgrade_files = result["files"]
                assert isinstance(upgrade_files, dict)
                for rel, state in upgrade_files.items():
                    print(f"{state:<12} {rel}")
            return 0
        try:
            result = status(root)
        except BlueprintError as exc:
            print(f"blueprint status failed: {exc}", file=sys.stderr)
            return 2
        if args.as_json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(
                f"blueprint: {result['blueprint']} "
                f"{result['installed_version']} ({result['version_state']})"
            )
            files = result["files"]
            assert isinstance(files, dict)
            for rel, state in files.items():
                print(f"{state:<10} {rel}")
        return 0
    if args.command == "reconcile":
        from hornero.reconciler.run import run_reconcile

        return run_reconcile(root, dry_run=args.dry_run)
    if args.command == "build":
        from hornero.build import run_build

        return run_build(root, args.spec_ids, backend=args.backend)
    if args.command == "reindex":
        from datetime import datetime, timezone

        from hornero import watermarks
        from hornero.memory.reindex import reindex

        knowledge_dir = root / ".hornero" / "knowledge"
        # The manifest embeds head_ref (reproducibility metadata) — its churn
        # is not content, or every commit would defeat the no-op discipline.
        exclude = frozenset({"manifest.json"})
        manifest_path = knowledge_dir / "manifest.json"
        old_manifest = (
            manifest_path.read_bytes() if manifest_path.is_file() else None
        )
        before = watermarks.content_snapshot([knowledge_dir], exclude)
        manifest = reindex(root)
        after = watermarks.content_snapshot([knowledge_dir], exclude)
        if after == before and old_manifest is not None:
            # SPEC-003 §5: no-op => no watermark write, no metadata churn.
            manifest_path.write_bytes(old_manifest)
            print("knowledge index already current")
            return 0
        watermarks.update(root, "reindex", {
            "git_head": watermarks.git_head(root),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "manifest_hash": after,
        })
        print(
            f"reindexed: {len(manifest['sources'])} source file(s), "
            f"{manifest.get('graph', {}).get('pages', 0)} graph page(s), "
            f"{manifest.get('graph', {}).get('edges', 0)} edge(s), "
            f"head_ref {manifest['head_ref'] or '(not a git repo)'}"
        )
        return 0
    if args.command == "report":
        from hornero.reports.run import run_report

        return run_report(root, only=args.only)
    if args.command == "runs":
        return _cmd_runs(args, root)
    if args.command == "scribe":
        from datetime import date

        from hornero.llm import LLMError, resolve_llm
        from hornero.scribe import ScribeError, scribe_run

        try:
            cfg = load_config(root)
        except ConfigError as exc:
            print(f"config error: {exc}", file=sys.stderr)
            return 1
        try:
            llm = resolve_llm(cfg, root, "scribe")
        except LLMError as exc:
            print(f"scribe model error: {exc}", file=sys.stderr)
            return 1
        if llm is None:
            print(
                "no model configured for the scribe "
                "(set models.scribe; MVP supports fake:<script.json>)",
                file=sys.stderr,
            )
            return 3
        try:
            return scribe_run(
                root, args.run_ref, llm,
                today=date.today().isoformat(), force=args.force,
            )
        except (FileNotFoundError, ScribeError, LLMError) as exc:
            print(f"scribe failed: {exc}", file=sys.stderr)
            return 2
    if args.command == "wiki":
        if args.wiki_command == "parrot":
            return _cmd_parrot_wiki(args, root)
        if args.wiki_command == "codex":
            return _cmd_codex_wiki(args, root)
        from hornero.llm import LLMError, model_name, resolve_llm
        from hornero.wiki import WikiError, wiki_init, wiki_update

        try:
            cfg = load_config(root)
        except ConfigError as exc:
            print(f"config error: {exc}", file=sys.stderr)
            return 1
        try:
            llm = resolve_llm(cfg, root, "wiki")
        except LLMError as exc:
            print(f"wiki model error: {exc}", file=sys.stderr)
            return 1
        if llm is None:
            print(
                "no model configured for the wiki "
                "(set models.wiki; MVP supports fake:<script.json>)",
                file=sys.stderr,
            )
            return 3
        fn = wiki_init if args.wiki_command == "init" else wiki_update
        try:
            return fn(root, llm, model=model_name(cfg, "wiki"))
        except (WikiError, LLMError) as exc:
            print(f"wiki {args.wiki_command} failed: {exc}", file=sys.stderr)
            return 1
    if args.command == "knowledge":
        return _cmd_knowledge(args, root)
    if args.command == "sdd":
        return _cmd_sdd(args, root)
    raise AssertionError("unreachable")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

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
    p_wiki = sub.add_parser("wiki", help="agent-facing living wiki (SPEC-003)")
    wiki_sub = p_wiki.add_subparsers(dest="wiki_command", required=True)
    wiki_sub.add_parser("init", help="first full wiki build")
    wiki_sub.add_parser("update", help="surgical refresh scoped by the watermark")

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
    root = Path.cwd()
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
            f"head_ref {manifest['head_ref'] or '(not a git repo)'}"
        )
        return 0
    if args.command == "report":
        from hornero.reports.run import run_report

        return run_report(root, only=args.only)
    if args.command == "runs":
        return _cmd_runs(args, root)
    if args.command == "wiki":
        from hornero.config import ConfigError, load_config
        from hornero.llm import model_name, resolve_llm
        from hornero.wiki import WikiError, wiki_init, wiki_update

        try:
            cfg = load_config(root)
        except ConfigError as exc:
            print(f"config error: {exc}", file=sys.stderr)
            return 1
        llm = resolve_llm(cfg, root, "wiki")
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
        except WikiError as exc:
            print(f"wiki {args.wiki_command} failed: {exc}", file=sys.stderr)
            return 1
    if args.command == "sdd":
        return _cmd_sdd(args, root)
    raise AssertionError("unreachable")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

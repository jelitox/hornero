"""hornero CLI (SPEC-001 §10). MVP surface:

    hornero init                      scaffold .hornero/ + product/ in an existing repo
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
_PRODUCT_DIRS = ("specs", "decisions", "reports")
_GITIGNORE_LINE = ".hornero/ledger.db*"  # includes SQLite -wal/-shm siblings


def _cmd_init(root: Path) -> int:
    hornero_dir = root / ".hornero"
    for name in _HORNERO_DIRS:
        d = hornero_dir / name
        d.mkdir(parents=True, exist_ok=True)
        (d / ".gitkeep").touch()
    for name in _PRODUCT_DIRS:
        d = root / "product" / name
        d.mkdir(parents=True, exist_ok=True)
        (d / ".gitkeep").touch()

    config = hornero_dir / "config.yaml"
    if not config.exists():  # never overwrite an existing config
        config.write_text(DEFAULT_CONFIG, encoding="utf-8")

    gitignore = root / ".gitignore"
    lines = gitignore.read_text(encoding="utf-8").splitlines() if gitignore.exists() else []
    if _GITIGNORE_LINE not in lines:
        content = "\n".join([*lines, _GITIGNORE_LINE]) + "\n"
        gitignore.write_text(content, encoding="utf-8")

    Ledger(hornero_dir / "ledger.db").close()  # idempotent schema init
    print(f"initialized hornero in {root}")
    return 0


def _cmd_status(root: Path) -> int:
    try:
        load_config(root)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 1

    corpus = SpecCorpus(root / "product" / "specs")
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
    p = sub.add_parser("init", help="scaffold .hornero/ + product/")
    p.add_argument("--hooks", action="store_true",
                   help="also install the post-merge reindex git hook (opt-in)")
    p.add_argument("--print-ci-hook", action="store_true",
                   help="print a CI reindex snippet and exit (writes nothing)")
    sub.add_parser("status", help="spec counts, inbox, index health")
    p = sub.add_parser("reconcile", help="poll -> deltas -> HITL -> apply")
    p.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("build", help="approved specs -> briefs -> dispatch")
    p.add_argument("spec_ids", nargs="*")
    p.add_argument("--backend", choices=["cli", "mock"])
    sub.add_parser("reindex", help="rebuild .hornero/knowledge/")
    p = sub.add_parser("report", help="regenerate product/reports/*.html")
    p.add_argument("--only")

    p_sdd = sub.add_parser("sdd", help="SDD toolkit management (SPEC-002)")
    sdd_sub = p_sdd.add_subparsers(dest="sdd_command", required=True)
    pi = sdd_sub.add_parser("install", help="install toolkit + scaffold + lockfile")
    pi.add_argument("--from", dest="source", help="git URL or local path")
    pi.add_argument("--ref", default=None)
    pi.add_argument("--force", action="store_true",
                    help="overwrite locally modified managed files")
    return parser


def _cmd_sdd(args: argparse.Namespace, root: Path) -> int:
    from datetime import datetime, timezone

    from hornero.config import ConfigError, load_config
    from hornero.sdd_toolkit.manifest import ManifestError
    from hornero.sdd_toolkit.upstream import UpstreamError

    try:
        cfg = load_config(root)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 1
    source = args.source or cfg.sdd_upstream
    if not source:
        print(
            "no toolkit upstream configured: pass --from <git-url|path> or set "
            "'sdd_upstream:' in .hornero/config.yaml",
            file=sys.stderr,
        )
        return 2
    ref = args.ref or cfg.sdd_ref

    if args.sdd_command == "install":
        from hornero.sdd_toolkit.install import install

        try:
            return install(
                root, source, ref, force=args.force,
                synced_at=datetime.now(timezone.utc).isoformat(),
            )
        except (UpstreamError, ManifestError) as exc:
            print(f"sdd install failed: {exc}", file=sys.stderr)
            return 1
    raise AssertionError("unreachable")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path.cwd()
    if args.command == "init":
        if args.print_ci_hook:
            from hornero.hooks import CI_SNIPPET

            print(CI_SNIPPET, end="")
            return 0
        rc = _cmd_init(root)
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
        from hornero.memory.reindex import reindex

        manifest = reindex(root)
        print(
            f"reindexed: {len(manifest['sources'])} source file(s), "
            f"head_ref {manifest['head_ref'] or '(not a git repo)'}"
        )
        return 0
    if args.command == "report":
        from hornero.reports.run import run_report

        return run_report(root, only=args.only)
    if args.command == "sdd":
        return _cmd_sdd(args, root)
    raise AssertionError("unreachable")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

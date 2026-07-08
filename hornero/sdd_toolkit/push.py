"""``sdd sync --push`` + ``--workspace`` (SPEC-002 §7, F4.5).

G3: improvements promote upstream via per-file, explicit, PR-gated pushes —
never direct to the default branch (asserted in code). R9: a secret-pattern
scan refuses to promote files that embed tokens (``--allow-secrets``
overrides for one run). All process execution goes through an injected
``runner`` — subprocess in prod, a recorder in tests, which must never
spawn a real ``gh``.
"""

import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# Secret shapes live in the shared redaction layer (SPEC-003 §9); push keeps
# refusal semantics (scan, don't rewrite) on top of the same pattern set.
from hornero.redact import SECRET_PATTERNS, scan_secrets  # noqa: F401
from hornero.sdd_toolkit.cli_sync import Echo, SyncError, cmd_sync
from hornero.sdd_toolkit.drift import DriftState, classify
from hornero.sdd_toolkit.lock import load_lock
from hornero.sdd_toolkit.manifest import load_manifest
from hornero.sdd_toolkit.upstream import UpstreamError, fetch_upstream


@dataclass
class RunResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


Runner = Callable[[list[str], Path], RunResult]

DEFAULT_BRANCHES = ("main", "master")


def subprocess_runner(cmd: list[str], cwd: Path) -> RunResult:
    """Prod runner. A missing binary (e.g. ``gh`` not installed) is a clear
    error, never a traceback."""
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    except FileNotFoundError:
        return RunResult(127, "", f"{cmd[0]}: command not found — is it installed?")
    return RunResult(proc.returncode, proc.stdout, proc.stderr)


def push(
    repo_root: Path,
    files: list[str],
    *,
    source: str,
    ref: str,
    runner: Runner,
    echo: Echo = print,
    allow_secrets: bool = False,
) -> int:
    lock = load_lock(repo_root)
    if lock is None:
        raise SyncError("no .hornero/sdd.lock — run 'hornero sdd install' first")
    checkout = fetch_upstream(source, ref, repo_root)
    if not checkout.refreshed:
        echo("warning: upstream unreachable — pushing against a stale cache")
    manifest, _ = load_manifest(checkout.root)
    drifts = {
        d.path: d for d in classify(checkout.root, repo_root, manifest, lock)
    }

    if not files:
        candidates = sorted(
            p for p, d in drifts.items() if d.state is DriftState.MODIFIED
        )
        raise SyncError(
            "push is per-file and explicit (R8): name the file(s) to promote"
            + (f"; modified candidates: {', '.join(candidates)}" if candidates
               else "; nothing is modified")
        )

    # 1. Only MODIFIED files are promotable.
    offenders = [
        f"{rel} ({drifts[rel].state.value if rel in drifts else 'not managed'})"
        for rel in files
        if rel not in drifts or drifts[rel].state is not DriftState.MODIFIED
    ]
    if offenders:
        echo(f"refusing to push non-modified file(s): {', '.join(offenders)}")
        return 1

    # 2. Secret scan (R9): refuse on match unless explicitly overridden.
    findings = {
        rel: hits
        for rel in files
        if (hits := scan_secrets((repo_root / rel).read_text(encoding="utf-8")))
    }
    if findings:
        for rel, hits in sorted(findings.items()):
            echo(f"secret scan: {rel}: {', '.join(hits)}")
        if not allow_secrets:
            echo("refusing to promote (override with --allow-secrets)")
            return 1
        echo("warning: secret scan overridden by --allow-secrets for this run")

    # 3. Branch + commit + PR in the upstream checkout, via the runner.
    branch = f"sdd-toolkit/promote-{repo_root.name}"
    assert branch.startswith("sdd-toolkit/") and branch not in DEFAULT_BRANCHES
    repo = repo_root.name
    title = (
        f"sdd-toolkit: promote {files[0]} from {repo}"
        if len(files) == 1
        else f"sdd-toolkit: promote {len(files)} files from {repo}"
    )
    body = "Promoted by `hornero sdd sync --push`:\n" + "".join(
        f"- {rel}\n" for rel in files
    )

    steps: list[list[str]] = [["git", "checkout", "-B", branch]]
    for step in steps:
        result = runner(step, checkout.root)
        if result.returncode != 0:
            echo(f"push failed at {' '.join(step)}: {result.stderr.strip()}")
            return 1
    for rel in files:  # copy AFTER the branch exists, so the commit sees them
        dest = checkout.root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo_root / rel, dest)
    for step in (
        ["git", "add", *files],
        ["git", "commit", "-m", title],
        ["git", "push", "-u", "origin", branch],
        ["gh", "pr", "create", "--title", title, "--body", body],
    ):
        result = runner(step, checkout.root)
        if result.returncode != 0:
            echo(f"push failed at {' '.join(step[:3])}: {result.stderr.strip()}")
            return 1
    pr_url = result.stdout.strip()
    echo(f"promoted {len(files)} file(s) on {branch}"
         + (f" — {pr_url}" if pr_url else ""))
    return 0


def cmd_workspace(
    workspace: Path,
    *,
    synced_at: str,
    force: bool = False,
    echo: Echo = print,
) -> int:
    """§7 fanout: pull-sync every immediate child carrying
    ``.hornero/sdd.lock`` (its lock is its sync identity); skip everything
    else."""
    if not workspace.is_dir():
        raise SyncError(f"{workspace} is not a directory")
    synced = skipped = failed = 0
    worst = 0
    for child in sorted(p for p in workspace.iterdir() if p.is_dir()):
        lock = load_lock(child)
        if lock is None:
            skipped += 1
            continue
        echo(f"--- {child.name}")

        def child_echo(message: str, name: str = child.name) -> None:
            echo(f"[{name}] {message}")

        try:
            rc = cmd_sync(
                child, lock.upstream, lock.upstream_ref,
                force=force, synced_at=synced_at, echo=child_echo,
            )
        except (SyncError, UpstreamError) as exc:
            echo(f"[{child.name}] sync failed: {exc}")
            rc = 1
        if rc != 0:
            failed += 1
        synced += 1
        worst = max(worst, rc)
    echo(
        f"workspace: {synced} repo(s) synced ({failed} with drift/errors), "
        f"{skipped} skipped (no .hornero/sdd.lock)"
    )
    return worst

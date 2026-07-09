"""``GitSource`` — code changes as requirement signals (SPEC-003 §6).

The reconciler's fourth built-in :class:`SignalSource`, **opt-in** via
``config.yaml: signal_sources: [inbox, git]``. Commits since the
``gitsource`` watermark become ONE digest signal per window: commit
messages + changed paths + stat summary — never full diffs (the reconciler
retrieves details on demand). Commits authored by hornero identities are
skipped: they already trace to specs via the ledger.

Purpose: spec drift from the code side — behavior that shipped without a
spec (candidate NEW: "formalize what was built") or against one
(CHANGED/OBSOLETE). Evidence cites commit SHAs + verbatim message excerpts;
the verbatim check applies unchanged.

Poll materializes the digest under ``.hornero/gitsource/`` (normalization
to a local file, the same contract the inbox relies on — deterministic per
window, so re-polling rewrites identical bytes). ``ack`` advances the
watermark to the window head and moves the digest to ``processed/`` so it
joins the knowledge corpus.
"""

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from hornero import watermarks
from hornero.ports import Signal
from hornero.redact import redact

SURFACE = "gitsource"
_BOT_MARKER = "hornero"  # author name/email substring => own dispatch


def _git(root: Path, *args: str) -> str:
    try:
        proc = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    return proc.stdout


class GitSource:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._dir = root / ".hornero" / "gitsource"

    def _commits(self, since: str | None) -> list[dict[str, str]]:
        rng = f"{since}..HEAD" if since else "HEAD"
        raw = _git(self._root, "log", "--format=%x1e%H%x1f%an%x1f%ae%x1f%B", rng)
        commits = []
        for chunk in raw.split("\x1e"):
            if not chunk.strip():
                continue
            sha, author, email, message = chunk.split("\x1f", 3)
            if _BOT_MARKER in author.lower() or _BOT_MARKER in email.lower():
                continue  # own dispatches already trace to specs
            stat = _git(self._root, "show", "--stat", "--format=", sha).strip()
            commits.append({
                "sha": sha, "author": author,
                "message": message.strip(), "stat": stat,
            })
        return commits

    def poll(self) -> list[Signal]:
        head = watermarks.git_head(self._root)
        if head is None:
            return []  # not a git repo / unborn HEAD
        wm = watermarks.get(self._root, SURFACE)
        since = str(wm.get("git_head") or "") if wm else None
        if since == head:
            return []
        commits = self._commits(since or None)
        if not commits:
            return []
        signal_id = f"git-{head[:12]}"
        blocks = [
            f"## commit {c['sha']}\nAuthor: {c['author']}\n\n{c['message']}\n\n"
            f"```\n{c['stat']}\n```"
            for c in commits
        ]
        digest = (
            f"# Git activity digest -> {head}\n\n"
            f"{len(commits)} commit(s) since the last reconcile watermark.\n\n"
            + "\n\n".join(blocks) + "\n"
        )
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"{signal_id}.md"
        path.write_text(redact(digest), encoding="utf-8")
        (self._dir / f"{signal_id}.json").write_text(
            json.dumps({"head": head}), encoding="utf-8"
        )
        ts = _git(self._root, "log", "-1", "--format=%ct").strip()
        return [Signal(
            signal_id=signal_id, kind="document", path=str(path),
            received_at=float(ts) if ts else 0.0,
        )]

    def ack(self, signal_id: str) -> None:
        sidecar = self._dir / f"{signal_id}.json"
        digest = self._dir / f"{signal_id}.md"
        if sidecar.is_file():
            head = str(json.loads(sidecar.read_text(encoding="utf-8"))["head"])
            watermarks.update(self._root, SURFACE, {
                "git_head": head,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            sidecar.unlink()
        if digest.is_file():
            processed = self._root / ".hornero" / "processed"
            processed.mkdir(parents=True, exist_ok=True)
            digest.rename(processed / digest.name)

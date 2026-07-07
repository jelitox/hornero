"""InboxSource: the MVP SignalSource (SPEC-001 §7 adapter table).

Polls ``.hornero/inbox/`` for dropped ``.md``/``.txt``/``.vtt`` files; acks
by moving them to ``.hornero/processed/``. Stateless by design: inbox
contents = pending, processed/ = acked. No watcher daemon — ``poll()`` is a
plain directory scan and never mutates.
"""

import datetime
import hashlib
import shutil
from pathlib import Path

from hornero.ports import Signal

_KIND_BY_SUFFIX = {
    ".md": "meeting_notes",
    ".txt": "document",
    ".vtt": "transcript",
}


def _signal_id(path: Path) -> str:
    """Stable id ``sig-<YYYYMMDD>-<hash6>``: date from the file's mtime,
    suffix from a content hash — the same file always yields the same id."""
    day = datetime.datetime.fromtimestamp(
        path.stat().st_mtime, tz=datetime.timezone.utc
    ).strftime("%Y%m%d")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:6]
    return f"sig-{day}-{digest}"


class InboxSource:
    """``root`` is the ``.hornero/`` directory."""

    def __init__(self, root: Path) -> None:
        self.inbox = root / "inbox"
        self.processed = root / "processed"

    def poll(self) -> list[Signal]:
        if not self.inbox.is_dir():
            return []
        signals: list[Signal] = []
        for path in sorted(self.inbox.iterdir()):
            kind = _KIND_BY_SUFFIX.get(path.suffix.lower())
            if kind is None or not path.is_file():
                continue  # unsupported extensions are ignored, never deleted
            signals.append(
                Signal(
                    signal_id=_signal_id(path),
                    kind=kind,
                    path=str(path.resolve()),
                    received_at=path.stat().st_mtime,
                )
            )
        return signals

    def ack(self, signal_id: str) -> None:
        """Move the signal's file to processed/. Idempotent: unknown or
        already-acked ids are silent no-ops."""
        for sig in self.poll():
            if sig["signal_id"] != signal_id:
                continue
            src = Path(sig["path"])
            self.processed.mkdir(parents=True, exist_ok=True)
            dest = self.processed / src.name
            n = 1
            while dest.exists():  # deterministic collision suffix
                dest = self.processed / f"{src.stem}-{n}{src.suffix}"
                n += 1
            shutil.move(str(src), str(dest))
            return

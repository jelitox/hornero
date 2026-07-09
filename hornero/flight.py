"""Flight recorder (SPEC-004 §3): the action stream is the ground truth.

Every dispatch MUST produce a trace: an append-only JSONL of normalized
events under ``.hornero/runs/<run_ref>/trace.jsonl``. Narrative layers
(scribe DRs, wiki) are indexes over this stream, never evidence on their
own. Events are **redacted at write time** — traces see everything the
agent saw, so they are the highest-risk surface.

zstd compression on close is feature-detected (``zstandard``); without it
the plain JSONL stays (traces are cheap either way; the format is what
matters). Gitignored by default.
"""

import hashlib
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from hornero.redact import redact

KINDS = frozenset({
    "run.started", "run.finished", "message", "thinking_summary",
    "tool_use", "tool_result", "error", "retry",
    "hitl.request", "hitl.decision",
})

RUNS_DIR = Path(".hornero") / "runs"


def runs_dir(root: Path) -> Path:
    return root / RUNS_DIR


class TraceWriter:
    """Sequenced, redacted, append-only event writer for one run."""

    def __init__(
        self,
        root: Path,
        run_ref: str,
        actor: str,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.run_ref = run_ref
        self.actor = actor
        self._clock = clock
        self._seq = 0
        self.path = runs_dir(root) / run_ref / "trace.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("", encoding="utf-8")

    def emit(
        self,
        kind: str,
        summary: str,
        payload: dict[str, Any] | None = None,
        *,
        actor: str | None = None,
    ) -> int:
        if kind not in KINDS:
            raise ValueError(f"unknown trace event kind {kind!r}")
        self._seq += 1
        event = {
            "seq": self._seq, "ts": self._clock(), "run_id": self.run_ref,
            "actor": actor or self.actor, "kind": kind, "summary": summary,
            "payload": payload or {},
        }
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(redact(json.dumps(event, ensure_ascii=False)) + "\n")
        return self._seq

    def close(self) -> Path:
        """Compress when zstandard is available; else the JSONL stands."""
        try:
            import zstandard  # type: ignore[import-not-found]
        except ImportError:
            return self.path
        data = self.path.read_bytes()
        packed = self.path.with_suffix(".jsonl.zst")
        packed.write_bytes(zstandard.ZstdCompressor().compress(data))
        self.path.unlink()
        self.path = packed
        return packed


def _trace_file(root: Path, run_ref: str) -> Path | None:
    base = runs_dir(root) / run_ref
    for name in ("trace.jsonl", "trace.jsonl.zst"):
        if (base / name).is_file():
            return base / name
    return None


def read_trace(root: Path, run_ref: str) -> list[dict[str, Any]]:
    path = _trace_file(root, run_ref)
    if path is None:
        raise FileNotFoundError(f"no trace for run {run_ref!r}")
    if path.suffix == ".zst":
        import zstandard  # type: ignore[import-not-found]

        text = zstandard.ZstdDecompressor().decompress(path.read_bytes()).decode()
    else:
        text = path.read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def parse_range(spec: str) -> tuple[int, int]:
    """``e#12:e#40`` (or ``e#12``) -> inclusive (12, 40)."""
    parts = spec.split(":")
    nums = []
    for part in parts:
        part = part.strip()
        if not part.startswith("e#"):
            raise ValueError(f"bad range {spec!r}: use e#N or e#N:e#M")
        nums.append(int(part[2:]))
    if len(nums) == 1:
        return nums[0], nums[0]
    if len(nums) != 2 or nums[0] > nums[1]:
        raise ValueError(f"bad range {spec!r}")
    return nums[0], nums[1]


def slice_events(
    events: list[dict[str, Any]],
    kinds: set[str] | None = None,
    span: tuple[int, int] | None = None,
) -> list[dict[str, Any]]:
    out = events
    if kinds:
        out = [e for e in out if e.get("kind") in kinds]
    if span:
        lo, hi = span
        out = [e for e in out if lo <= int(e.get("seq", -1)) <= hi]
    return out


# --- Claude Code transcript adoption (SPEC-004 §3.1, OQ13: tolerant) -------

def _normalize_entry(obj: dict[str, Any]) -> list[tuple[str, str]]:
    """Best-effort (kind, summary) events from one transcript line. The
    format is undocumented and unstable across versions — unknown shapes
    degrade to ``message``, never crash; the raw payload is preserved."""
    etype = str(obj.get("type", ""))
    events: list[tuple[str, str]] = []
    message = obj.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "tool_use":
                events.append(("tool_use", f"{block.get('name', 'tool')}"))
            elif btype == "tool_result":
                events.append(("tool_result", "tool result"))
            elif btype == "thinking":
                events.append(("thinking_summary", "(thinking)"))
            elif btype == "text":
                text = str(block.get("text", ""))[:120]
                events.append(("message", f"{etype or 'message'}: {text}"))
    if not events:
        summary = str(obj.get("summary") or etype or "entry")[:120]
        events.append(("message", summary))
    return events


def adopt_transcript(root: Path, transcript: Path) -> str:
    """Copy a session transcript into ``.hornero/runs/`` as a normalized
    trace. Returns the new run_ref; the caller registers it in the ledger."""
    digest = hashlib.sha256(transcript.read_bytes()).hexdigest()[:12]
    run_ref = f"adopted-{digest}"
    writer = TraceWriter(root, run_ref, "adopted:claude-code")
    writer.emit("run.started", f"adopted transcript {transcript.name}")
    for line in transcript.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue  # tolerant: a corrupt line never sinks the adoption
        if not isinstance(obj, dict):
            continue
        for kind, summary in _normalize_entry(obj):
            writer.emit(kind, summary, {"raw": obj})
    writer.emit("run.finished", "adoption complete")
    writer.close()
    return run_ref

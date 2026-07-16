"""Dispatch bridge: spec -> BuildBrief -> backend (SPEC-001 §7, OQ5).

``multicoders`` is not pinned in this repo (SPEC-001 OQ5), so the built-in
deterministic :class:`MockBackend` is the first-class default and real
``multicoders.backends`` is feature-detected — same pattern the knowledge
layer uses for parrot. Hard rules (CLAUDE.md invariant 3, NG2):

- ``api`` is NEVER a fallback: it runs only as the explicit, user-written
  FIRST entry of ``dispatch.backend_order``. Automatic resolution skips it.
- No token/credential plumbing of any kind lives here. CliBackend is
  BYO-auth in the user's own session.
- ``dispatch()`` never raises for operational failures — they come back as
  ``status="failed"`` / ``"needs_human"`` with a written log.
"""

import importlib.util
import json
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from hornero.criteria import parse_criteria
from hornero.redact import redact
from hornero.flight import TraceWriter
from hornero.lifecycle import SpecDoc
from hornero.ports import BuildBrief, BuildResult

_ADR_REF = "ADR-"


def _multicoders_available() -> bool:
    try:
        return importlib.util.find_spec("multicoders.backends") is not None
    except (ModuleNotFoundError, ValueError):
        return False


def brief_from_spec(
    doc: SpecDoc, repo_path: str, allowlist: Sequence[str], decisions_dir: Path
) -> BuildBrief:
    """Render one approved spec into a BuildBrief. ADRs referenced in the
    spec body are inlined into the description; unparseable acceptance
    criteria abort the brief (a spec with broken criteria must not dispatch)."""
    parse_criteria(doc.acceptance_criteria, allowlist)  # raises on broken input

    description = doc.body.strip()
    linked = [
        p
        for p in (sorted(decisions_dir.glob("ADR-*.md")) if decisions_dir.is_dir() else [])
        if p.stem.split("-", 2)[0] + "-" + p.stem.split("-", 2)[1] in doc.body
        or p.stem in doc.body
    ]
    for adr in linked:
        description += (
            f"\n\n---\n### Linked decision {adr.stem}\n\n"
            + adr.read_text(encoding="utf-8").strip()
        )
    description += (
        "\n\n---\n### Write-back contract (SPEC-001 F4)\n\n"
        "Ship in the SAME branch/PR as the code: this spec file with its "
        "frontmatter transitioned to `review`, and regenerated "
        "`sdd/reports/` so code + spec + reports land atomically."
    )
    return BuildBrief(
        spec_id=doc.spec_id,
        kind=doc.kind,
        summary=doc.title,
        description=description,
        acceptance_criteria=list(doc.acceptance_criteria),
        repo_path=repo_path,
    )


class Backend(Protocol):
    name: str

    def run(self, brief: BuildBrief, trace: TraceWriter) -> BuildResult: ...


class MockBackend:
    """Deterministic fake: same brief + same counter state => same result.
    Emits a synthetic event stream into the trace — this is the e2e test
    path (real engine, simulated externals) and the F9 fixture."""

    name = "mock"

    def __init__(self, root: Path, counter: int = 1) -> None:
        self._logs = root / ".hornero" / "dispatch-logs"
        self._counter = counter

    def run(self, brief: BuildBrief, trace: TraceWriter) -> BuildResult:
        self._logs.mkdir(parents=True, exist_ok=True)
        n = self._counter
        self._counter += 1
        trace.emit("message", f"MOCK BUILD {brief['spec_id']} (#{n}): "
                              f"{brief['summary']}")
        trace.emit("tool_use", f"Edit src/{brief['spec_id'].lower()}.py (+12 -3)",
                   {"criteria": list(brief["acceptance_criteria"])})
        trace.emit("tool_result", "edit applied")
        # Simulate the write-back contract: the "PR" carries the spec updated
        # to review alongside the code (what a real backend must do).
        (self._logs / f"{brief['spec_id']}.pr-contents.md").write_text(
            f"<!-- simulated PR write-back: status -> review -->\n"
            f"{brief['description']}\n",
            encoding="utf-8",
        )
        return BuildResult(
            status="completed",
            pr_url=f"https://example.invalid/pr/{brief['spec_id']}-{n}",
            branch=f"hornero/{brief['spec_id']}",
            trace_path="",  # the dispatcher owns the trace location
        )


class _UnavailableBackend:
    """Stands in for a configured-but-absent real backend: yields an honest
    ``needs_human`` result instead of crashing or substituting."""

    def __init__(self, name: str, root: Path, reason: str) -> None:
        self.name = name
        self._logs = root / ".hornero" / "dispatch-logs"
        self._reason = reason

    def run(self, brief: BuildBrief, trace: TraceWriter) -> BuildResult:
        trace.emit("error", f"backend '{self.name}' unavailable: {self._reason}")
        return BuildResult(
            status="needs_human", pr_url=None, branch=None, trace_path=""
        )


class CliBackend:
    """BYO-auth coding backend using an explicit argv and JSON stdin/stdout."""

    name = "cli"

    def __init__(
        self, root: Path, command: Sequence[str], *, timeout: float,
        max_output_bytes: int,
    ) -> None:
        self._root = root
        self._command = list(command)
        self._timeout = timeout
        self._max_output = max_output_bytes

    def run(self, brief: BuildBrief, trace: TraceWriter) -> BuildResult:
        trace.emit("tool_use", f"coding CLI: {self._command[0]}")
        try:
            proc = subprocess.run(
                self._command, cwd=self._root,
                input=json.dumps(brief, ensure_ascii=False),
                capture_output=True, text=True, timeout=self._timeout,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            trace.emit("error", f"coding CLI failed: {exc}")
            return BuildResult(
                status="failed", pr_url=None, branch=None, trace_path=""
            )
        stdout = proc.stdout[:self._max_output]
        stderr = redact(proc.stderr[:self._max_output])
        if stderr:
            trace.emit("message", stderr)
        if proc.returncode != 0:
            trace.emit("error", f"coding CLI exited {proc.returncode}")
            return BuildResult(
                status="failed", pr_url=None, branch=None, trace_path=""
            )
        try:
            payload = json.loads(stdout)
            status = str(payload["status"])
            if status not in ("completed", "failed", "needs_human"):
                raise ValueError("invalid status")
            result = BuildResult(
                status=status,
                pr_url=str(payload["pr_url"]) if payload.get("pr_url") else None,
                branch=str(payload["branch"]) if payload.get("branch") else None,
                trace_path="",
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            trace.emit("error", f"coding CLI returned invalid JSON result: {exc}")
            return BuildResult(
                status="needs_human", pr_url=None, branch=None, trace_path=""
            )
        trace.emit("tool_result", f"coding CLI result: {result['status']}")
        return result


class MulticodersDispatch:
    """DispatchPort adapter. Resolution walks ``backend_order`` and picks the
    first AVAILABLE backend — except ``api``, which is honored only as the
    explicit first entry and never reached by falling through a failed one."""

    def __init__(
        self, backend_order: Sequence[str], root: Path, *,
        cli_command: Sequence[str] = (), timeout: float = 900.0,
        max_output_bytes: int = 1_000_000,
    ) -> None:
        self._root = root
        self._cli_command = list(cli_command)
        self._timeout = timeout
        self._max_output_bytes = max_output_bytes
        self._backend = self._resolve(list(backend_order))

    def _real_backend(self, name: str) -> Backend:
        # Deferred integration (OQ5): multicoders.backends is importable but
        # untested in this repo; refuse to guess its API and route to a human.
        return _UnavailableBackend(
            name, self._root,
            "multicoders integration pending (SPEC-001 OQ5); "
            "use backend 'mock' or run the build manually",
        )

    def _resolve(self, order: list[str]) -> Backend:
        for i, name in enumerate(order):
            if name == "mock":
                return MockBackend(self._root)
            if name == "cli":
                if self._cli_command:
                    return CliBackend(
                        self._root, self._cli_command, timeout=self._timeout,
                        max_output_bytes=self._max_output_bytes,
                    )
                if _multicoders_available():
                    return self._real_backend("cli")
                return _UnavailableBackend(
                    "cli", self._root, "multicoders is not installed"
                )
            if name == "api":
                if i != 0:
                    continue  # NEVER a fallback — skip unless explicit first
                if _multicoders_available():
                    return self._real_backend("api")
                return _UnavailableBackend(
                    "api", self._root, "multicoders is not installed"
                )
        return _UnavailableBackend(
            "none", self._root, f"no usable backend in order {order!r}"
        )

    @property
    def backend_name(self) -> str:
        return self._backend.name

    def dispatch(self, brief: BuildBrief, run_ref: str | None = None) -> BuildResult:
        """SPEC-004 §3.1 capture contract: every dispatch produces a trace.
        ``run_ref`` shares the ledger's run-id namespace; when omitted a
        spec-derived ref keeps ad-hoc dispatches traceable too."""
        run_ref = run_ref or f"run-{brief['spec_id'].lower()}"
        trace = TraceWriter(
            self._root, run_ref, f"dispatch:{self._backend.name}"
        )
        trace.emit(
            "run.started",
            f"dispatch {brief['spec_id']} via {self._backend.name}",
            {"summary": brief["summary"]},
        )
        try:
            result = self._backend.run(brief, trace)
        except Exception as exc:
            trace.emit("error", f"backend {self._backend.name} failed: {exc}")
            result = BuildResult(
                status="failed", pr_url=None, branch=None, trace_path=""
            )
        trace.emit(
            "run.finished", f"status {result['status']}",
            {"pr_url": result["pr_url"]},
        )
        result["trace_path"] = str(trace.close())
        return result

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
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from hornero.criteria import parse_criteria
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
        "`product/reports/` so code + spec + reports land atomically."
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

    def run(self, brief: BuildBrief) -> BuildResult: ...


class MockBackend:
    """Deterministic fake: same brief + same counter state => same result.
    Writes a log under ``.hornero/dispatch-logs/`` — this is the e2e test
    path (real engine, simulated externals)."""

    name = "mock"

    def __init__(self, root: Path, counter: int = 1) -> None:
        self._logs = root / ".hornero" / "dispatch-logs"
        self._counter = counter

    def run(self, brief: BuildBrief) -> BuildResult:
        self._logs.mkdir(parents=True, exist_ok=True)
        n = self._counter
        self._counter += 1
        log_path = self._logs / f"{brief['spec_id']}.log"
        log_path.write_text(
            f"MOCK BUILD {brief['spec_id']} (#{n})\n"
            f"summary: {brief['summary']}\n"
            f"criteria: {brief['acceptance_criteria']}\n",
            encoding="utf-8",
        )
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
            log_path=str(log_path),
        )


class _UnavailableBackend:
    """Stands in for a configured-but-absent real backend: yields an honest
    ``needs_human`` result instead of crashing or substituting."""

    def __init__(self, name: str, root: Path, reason: str) -> None:
        self.name = name
        self._logs = root / ".hornero" / "dispatch-logs"
        self._reason = reason

    def run(self, brief: BuildBrief) -> BuildResult:
        self._logs.mkdir(parents=True, exist_ok=True)
        log_path = self._logs / f"{brief['spec_id']}.log"
        log_path.write_text(
            f"backend '{self.name}' unavailable: {self._reason}\n", encoding="utf-8"
        )
        return BuildResult(
            status="needs_human", pr_url=None, branch=None, log_path=str(log_path)
        )


class MulticodersDispatch:
    """DispatchPort adapter. Resolution walks ``backend_order`` and picks the
    first AVAILABLE backend — except ``api``, which is honored only as the
    explicit first entry and never reached by falling through a failed one."""

    def __init__(self, backend_order: Sequence[str], root: Path) -> None:
        self._root = root
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

    def dispatch(self, brief: BuildBrief) -> BuildResult:
        return self._backend.run(brief)

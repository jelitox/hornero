"""RepoTracker: the spec file IS the ticket (SPEC-001 §7 adapter table).

``transition`` edits only the frontmatter status line (via the lifecycle
round-trip guarantee); ``comment`` appends a dated bullet to the spec's
``## Log`` section. No Jira, no GitHub — the repo is the tracker (G4).

``GitHubIssuesTracker`` (optional, feature-flagged per §7) is deferred and
deliberately not implemented here.
"""

import datetime
import re
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from hornero.lifecycle import SpecDoc, parse_spec, transition, write_spec

_HEADING = re.compile(r"^## ", re.MULTILINE)


def _today() -> str:
    return datetime.date.today().isoformat()


class UnknownRefError(KeyError):
    """Raised when a ref does not resolve to a spec file."""


class RepoTracker:
    def __init__(self, specs_dir: Path, clock: Callable[[], str] = _today) -> None:
        self.specs_dir = specs_dir
        self._clock = clock

    def _doc(self, ref: str) -> SpecDoc:
        if self.specs_dir.is_dir():
            for path in sorted(self.specs_dir.glob("SPEC-*.md")):
                doc = parse_spec(path)
                if doc.spec_id == ref:
                    return doc
        raise UnknownRefError(f"no spec with id {ref!r} under {self.specs_dir}")

    # -- TrackerPort ---------------------------------------------------------
    def upsert(self, spec_path: str) -> str:
        """Validate the spec file (parseable frontmatter) and return its ref."""
        return parse_spec(Path(spec_path)).spec_id

    def transition(self, ref: str, status: str) -> None:
        doc = self._doc(ref)
        write_spec(transition(doc, status))  # IllegalTransition propagates

    def comment(self, ref: str, body: str) -> None:
        doc = self._doc(ref)
        bullet = f"- {self._clock()} — {body}\n"
        text = doc.body
        idx = text.find("## Log")
        if idx < 0:
            sep = "\n" if text.endswith("\n") else "\n\n"
            new_body = f"{text}{sep}## Log\n\n{bullet}"
        else:
            nxt = _HEADING.search(text, idx + len("## Log"))
            insert_at = nxt.start() if nxt else len(text)
            before = text[:insert_at].rstrip("\n") + "\n" + bullet
            after = text[insert_at:]
            new_body = before + ("\n" + after if after else "")
        write_spec(replace(doc, body=new_body))

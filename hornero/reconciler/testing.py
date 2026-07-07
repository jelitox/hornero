"""FakeLLM: the deterministic test double for :class:`~hornero.reconciler.draft.LLMPort`.

Shipped in package code (not tests/) so e2e fixtures, downstream repos, and
the ``fake:<script.json>`` model configuration can reuse it — the
real-engine / simulated-externals pattern. Loud by design: an unexpected
prompt raises instead of returning something lenient.
"""

import json
from pathlib import Path


class UnexpectedPromptError(AssertionError):
    pass


class FakeLLM:
    """``responses`` maps a distinctive substring of the *user* prompt to the
    canned response returned for it. First match (insertion order) wins."""

    def __init__(self, responses: dict[str, str]) -> None:
        self._responses = dict(responses)
        self.calls: list[tuple[str, str]] = []

    @classmethod
    def from_file(cls, path: Path) -> "FakeLLM":
        """Load a ``{substring: response}`` script. Responses may be given
        as JSON objects instead of strings; they are re-serialized."""
        data = json.loads(path.read_text(encoding="utf-8"))
        responses = {
            key: value if isinstance(value, str) else json.dumps(value)
            for key, value in data.items()
        }
        return cls(responses)

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        for key, response in self._responses.items():
            if key in user:
                return response
        raise UnexpectedPromptError(
            f"FakeLLM has no scripted response matching this prompt: {user[:200]!r}"
        )

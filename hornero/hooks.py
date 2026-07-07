"""Merge -> reindex hooks (SPEC-001 §12 F4, §1 step 5).

Installing anything into a developer's ``.git/hooks`` is a surprising
mutation, so it is strictly opt-in (``hornero init --hooks``), idempotent
(marker block, re-install replaces only our block), and refuses to touch a
foreign hook. The CI variant is only ever PRINTED for the user to paste —
no workflow files are written into target repos.
"""

import stat
from pathlib import Path

MARKER_BEGIN = "# >>> hornero post-merge >>>"
MARKER_END = "# <<< hornero post-merge <<<"

_HOOK_BLOCK = f"""{MARKER_BEGIN}
# Reindex the hornero knowledge base after every merge so the next signal
# is reconciled against the BUILT state (SPEC-001 §1 step 5).
if command -v hornero >/dev/null 2>&1; then
    hornero reindex || echo "hornero reindex failed (non-fatal)" >&2
else
    echo "hornero not on PATH; skipping reindex" >&2
fi
{MARKER_END}
"""

CI_SNIPPET = """\
# Paste into your CI (example: GitHub Actions). Runs `hornero reindex`
# after merges to the default branch and commits the refreshed index.
name: hornero-reindex
on:
  push:
    branches: [main]
jobs:
  reindex:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install hornero
      - run: hornero reindex
      - run: |
          git config user.name hornero-bot
          git config user.email hornero-bot@invalid
          git add .hornero/knowledge/
          git diff --cached --quiet || git commit -m "chore: hornero reindex"
          git push
"""


class HookError(RuntimeError):
    pass


def install_post_merge_hook(root: Path) -> str:
    """Install (or refresh) the hornero block in ``.git/hooks/post-merge``.
    Raises :class:`HookError` on a non-git dir or a foreign hook."""
    hooks_dir = root / ".git" / "hooks"
    if not hooks_dir.is_dir():
        raise HookError(f"{root} is not a git repository (no .git/hooks)")
    hook = hooks_dir / "post-merge"
    if hook.exists():
        text = hook.read_text(encoding="utf-8")
        if MARKER_BEGIN not in text:
            raise HookError(
                f"{hook} already exists and is not hornero's — refusing to "
                "clobber it; add the reindex call manually"
            )
        head, rest = text.split(MARKER_BEGIN, 1)
        _, tail = rest.split(MARKER_END, 1)
        new_text = head + _HOOK_BLOCK.rstrip("\n") + tail
    else:
        new_text = "#!/bin/sh\n" + _HOOK_BLOCK
    hook.write_text(new_text, encoding="utf-8")
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return f"installed post-merge hook at {hook}"

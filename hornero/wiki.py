"""Agent-facing living wiki (SPEC-003 §3, §5, §7).

``wiki/`` is the second projection of the knowledge layer: linked Markdown
whose primary consumer is the **next agent run**. Generation is LLM-drafted
but mechanically gated: quickstart is mandatory (W1), stub pages are
rejected (W2), relative links must resolve (link-checker), formatting-only
edits are reverted (U3), and the diff budget (U2) bounds how much one
change window may touch. The no-op discipline (§5) makes scheduled updates
churn-free, and an empty change window never even calls the model.
"""

import json
import os.path
import re
import subprocess
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from hornero import watermarks
from hornero.reconciler.draft import LLMPort
from hornero.redact import redact

Echo = Callable[[str], None]

SECTIONS = ("architecture", "workflows", "domain", "operations")
_SOURCE_EXTS = {".py", ".ts", ".tsx", ".js", ".go", ".rs", ".java", ".rb", ".c",
                ".cpp", ".h", ".cs", ".php"}
_SKIP_DIRS = {".git", ".hornero", ".venv", "node_modules", "wiki", "__pycache__"}
_LINK = re.compile(r"\[[^\]]*\]\(([^)#][^)]*)\)")
SMALL_REPO_FILES = 10
SMALL_REPO_MAX_PAGES = 3

INIT_SYSTEM = """\
You are hornero's wiki generator. Produce an agent-facing wiki for this
repository as STRICT JSON: {"pages": [{"path": "quickstart.md", "content":
"..."}, ...]}.

Rules (W1-W8): quickstart.md is mandatory — a zero-context reader starts
there and can navigate everywhere. No stub pages, no file inventories; small
repos get quickstart plus at most 1-2 pages. One canonical home per concept;
other pages link. Explain WHY code exists, include change-oriented guidance
(where to start, what to watch out for, which tests/gates matter). Existing
docs are primary sources to synthesize, never copy wholesale. Ground every
claim in the provided context. Section directories allowed: architecture/,
workflows/, domain/, operations/. Relative links only, and only to pages you
emit or files that exist. Output JSON only.
"""

UPDATE_SYSTEM = """\
You are hornero's wiki updater. Given the change window and the current wiki,
produce STRICT JSON: {"impact_plan": [{"change": "...", "page": "...",
"edit": "...", "why": "..."}], "edits": [{"path": "...", "content": "..."}],
"reason": "..."}.

Contract (U1-U4): only edit what the impact plan traces to a change in the
window. Decision records (sdd/decisions/DR-*.md) are the decision history:
link the relevant DRs from affected area pages and cite the DR when
promoting one of its durable learnings into a "what to watch out for" note
— never restate a DR's content as the wiki's own. Small windows (<=5 changed files) touch at most 1-2 pages; touching
more than 3 pages requires a stated reason. NEVER reflow, reorder, or polish
prose whose meaning is intact — formatting-only edits are reverted
mechanically. Prefer replacing one stale sentence over adding paragraphs; a
legitimate outcome is zero edits. Each edit carries the COMPLETE new page
content. Output JSON only.
"""


class WikiError(RuntimeError):
    pass


def wiki_dir(root: Path) -> Path:
    return root / "wiki"


def _git(root: Path, *args: str) -> str:
    try:
        proc = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    return proc.stdout


def _primary_source_count(root: Path) -> int:
    count = 0
    for p in root.rglob("*"):
        if any(part in _SKIP_DIRS for part in p.parts):
            continue
        if p.is_file() and p.suffix in _SOURCE_EXTS:
            count += 1
    return count


def _context_block(root: Path) -> str:
    """Discovery context. W8: the persisted knowledge index is the primary
    research surface; raw file listing is the fallback framing."""
    parts: list[str] = []
    readme = root / "README.md"
    if readme.is_file():
        parts.append("## README\n\n" + readme.read_text(encoding="utf-8")[:4000])
    specs = sorted((root / "sdd" / "specs").glob("*.md"))
    if specs:
        parts.append("## Specs\n\n" + "\n".join(f"- {p.name}" for p in specs))
    from hornero.memory.knowledge import open_knowledge

    hits = open_knowledge(root).retrieve("architecture overview purpose", k=5)
    if hits:
        parts.append("## Retrieved context\n\n" + "\n\n".join(
            f"### {h.path}\n{h.excerpt[:800]}" for h in hits
        ))
    tree = sorted(
        p.name + ("/" if p.is_dir() else "")
        for p in root.iterdir() if p.name not in _SKIP_DIRS
    )
    parts.append("## Top-level tree\n\n" + "\n".join(tree))
    return "\n\n".join(parts)


def _validate_paths(pages: dict[str, str]) -> None:
    if "quickstart.md" not in pages:
        raise WikiError("W1 violated: quickstart.md is mandatory")
    for rel in pages:
        p = Path(rel)
        if p.is_absolute() or ".." in p.parts or p.suffix != ".md":
            raise WikiError(f"illegal wiki path {rel!r}")
        if len(p.parts) == 2 and p.parts[0] not in SECTIONS:
            raise WikiError(f"unknown wiki section {p.parts[0]!r} for {rel!r}")
        if len(p.parts) > 2:
            raise WikiError(f"wiki nests at most one section level: {rel!r}")


def _check_stubs(pages: dict[str, str]) -> None:
    for rel, content in pages.items():
        if len(content.strip()) < 80:
            raise WikiError(f"W2 violated: {rel!r} is a stub")


def _check_links(root: Path, pages: dict[str, str]) -> list[str]:
    """Every relative link resolves to an emitted page, an existing wiki
    page, or a repo file. Returns broken 'page -> target' entries."""
    existing = {
        p.relative_to(wiki_dir(root)).as_posix()
        for p in wiki_dir(root).rglob("*.md")
    } if wiki_dir(root).is_dir() else set()
    known = set(pages) | existing
    broken: list[str] = []
    for rel, content in pages.items():
        base = Path(rel).parent
        for target in _LINK.findall(content):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            norm = os.path.normpath((base / target).as_posix())
            in_wiki = norm in known
            in_repo = (wiki_dir(root) / base / target).resolve().exists() or (
                (root / target.lstrip("./")).exists()
            )
            if not (in_wiki or in_repo):
                broken.append(f"{rel} -> {target}")
    return broken


def _parse_pages(raw: str, key: str = "pages") -> dict[str, str]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise WikiError(f"model returned invalid JSON: {exc}") from exc
    items = data.get(key, [])
    if not isinstance(items, list):
        raise WikiError(f"model JSON {key!r} must be a list")
    return {str(e["path"]): str(e["content"]) for e in items}


def _write_pages(root: Path, pages: dict[str, str]) -> None:
    for rel, content in pages.items():
        dest = wiki_dir(root) / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(redact(content), encoding="utf-8")


def _stamp(root: Path, model: str, content_hash: str, now_iso: str | None) -> None:
    watermarks.update(root, "wiki", {
        "git_head": watermarks.git_head(root),
        "updated_at": now_iso or datetime.now(timezone.utc).isoformat(),
        "model": model,
        "content_hash": content_hash,
    })


def wiki_init(
    root: Path, llm: LLMPort, *, model: str = "(unknown)",
    now_iso: str | None = None, echo: Echo = print,
) -> int:
    raw = llm.complete(INIT_SYSTEM, _context_block(root))
    pages = _parse_pages(raw)
    _validate_paths(pages)
    _check_stubs(pages)
    if _primary_source_count(root) <= SMALL_REPO_FILES and len(pages) > SMALL_REPO_MAX_PAGES:
        raise WikiError(
            f"W2 violated: small repo, at most {SMALL_REPO_MAX_PAGES} pages "
            f"(model proposed {len(pages)})"
        )
    # SPEC-004 §5: quickstart is the decision-history entrypoint.
    if "sdd/decisions" not in pages["quickstart.md"]:
        pages["quickstart.md"] += (
            "\n## Decision history\n\n"
            "Agent decision records (why the code looks the way it does) "
            "live in [sdd/decisions/](../sdd/decisions/).\n"
        )
    broken = _check_links(root, pages)
    if broken:
        raise WikiError("broken wiki links: " + "; ".join(broken))
    _write_pages(root, pages)
    _stamp(root, model, watermarks.content_snapshot([wiki_dir(root)]), now_iso)
    echo(f"wiki: {len(pages)} page(s) written")
    return 0


def _normalized(text: str) -> list[str]:
    """U3 guard basis: content modulo whitespace and line ordering."""
    return sorted(line.strip() for line in text.splitlines() if line.strip())


def _own_output(path: str) -> bool:
    """The wiki's own pages and hornero metadata are never analysis input —
    otherwise the commit that lands a wiki update would trigger the next one
    forever (churn)."""
    return path.startswith(("wiki/", ".hornero/"))


def _change_window(root: Path, since: str | None) -> tuple[str, list[str]]:
    """Human-readable window block + the list of changed files (own outputs
    filtered out). An empty file list means there is nothing to analyze."""
    changed: set[str] = set()
    if since:
        files = _git(root, "diff", "--name-only", f"{since}..HEAD")
        changed.update(
            li for li in files.splitlines() if li.strip() and not _own_output(li)
        )
    dirty = _git(root, "diff", "--name-only")
    changed.update(
        li for li in dirty.splitlines() if li.strip() and not _own_output(li)
    )
    if not changed:
        return "", []
    lines = []
    if since:
        subjects = _git(root, "log", "--format=%h %s", f"{since}..HEAD")
        if subjects.strip():
            lines.append("## Commits since last wiki sync\n\n" + subjects.strip())
    lines.append("## Changed files in the window\n\n" + "\n".join(sorted(changed)))
    return "\n\n".join(lines), sorted(changed)


def wiki_update(
    root: Path, llm: LLMPort, *, model: str = "(unknown)",
    now_iso: str | None = None, echo: Echo = print,
) -> int:
    wm = watermarks.get(root, "wiki")
    if wm is None or not wiki_dir(root).is_dir():
        # §4: missing/invalid watermark => full run (init semantics)
        return wiki_init(root, llm, model=model, now_iso=now_iso, echo=echo)

    since = str(wm.get("git_head") or "") or None
    window, changed = _change_window(root, since)
    tree_hash = watermarks.content_snapshot([wiki_dir(root)])
    if not window and tree_hash == wm.get("content_hash"):
        echo("wiki already current")  # empty window: the model is never called
        return 0

    current = {
        p.relative_to(wiki_dir(root)).as_posix(): p.read_text(encoding="utf-8")
        for p in sorted(wiki_dir(root).rglob("*.md"))
    }
    user = window + "\n\n## Current wiki\n\n" + "\n\n".join(
        f"### {rel}\n\n{content}" for rel, content in current.items()
    )
    try:
        data = json.loads(llm.complete(UPDATE_SYSTEM, user))
    except json.JSONDecodeError as exc:
        raise WikiError(f"model returned invalid JSON: {exc}") from exc
    edits = {str(e["path"]): str(e["content"]) for e in data.get("edits", [])}

    # U2 diff budget
    if len(changed) <= 5 and len(edits) > 2:
        raise WikiError(
            f"U2 violated: {len(changed)} changed file(s) cannot justify "
            f"{len(edits)} page edits"
        )
    if len(edits) > 3 and not str(data.get("reason", "")).strip():
        raise WikiError("U2 violated: >3 page edits require a stated reason")
    if len(edits) > 3:
        echo(f"wide edit justified: {data['reason']}")

    # U3 formatting-only guard
    for rel in [r for r in edits if r in current]:
        if _normalized(edits[rel]) == _normalized(current[rel]):
            echo(f"reverted formatting-only edit: {rel}")
            del edits[rel]

    if edits:
        merged = {**current, **edits}
        _validate_paths(merged)
        _check_stubs(edits)
        broken = _check_links(root, merged)
        if broken:
            raise WikiError("broken wiki links: " + "; ".join(broken))
        _write_pages(root, edits)

    after = watermarks.content_snapshot([wiki_dir(root)])
    if after == wm.get("content_hash"):
        # Content is a no-op, but the WINDOW was analyzed: advance the
        # watermark head so the same window is never re-analyzed (OQ-level
        # refinement of §5 — otherwise every scheduled run re-pays the model
        # call for an already-vetted window).
        _stamp(root, model, after, now_iso)
        echo("wiki already current")
        return 0
    _stamp(root, model, after, now_iso)
    echo(f"wiki: {len(edits)} page(s) updated")
    return 0

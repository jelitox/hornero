"""ai-parrot LLM-wiki bridge and native coding-agent integrations.

The bridge deliberately uses ``wikitoolkit`` as the compatibility boundary:
Hornero does not import ai-parrot's internal store implementation, while the
optional ``knowledge`` extra provides the supported CLI.  The installers wire
the same query-first workflow into Codex, Claude Code and Gemini CLI using each
agent's native project instructions, skills and lifecycle-hook contract.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath
from typing import Any, TextIO

CONFIG_REL = Path(".parrot/wiki.json")
DEFAULT_STORAGE = ".parrot/wiki"

AGENTS_BEGIN = "<!-- parrot:wiki:codex:begin -->"
AGENTS_END = "<!-- parrot:wiki:codex:end -->"
HOOK_COMMAND = "hornero wiki codex hook"
HOOK_MATCHER = "^(Bash|Grep|Glob|Read)$"
CLAUDE_BEGIN = "<!-- parrot:wiki:claude:begin -->"
CLAUDE_END = "<!-- parrot:wiki:claude:end -->"
CLAUDE_HOOK_COMMAND = "hornero wiki claude hook"
CLAUDE_HOOK_MATCHER = "^(Bash|Grep|Glob|Read)$"
GEMINI_BEGIN = "<!-- parrot:wiki:gemini:begin -->"
GEMINI_END = "<!-- parrot:wiki:gemini:end -->"
GEMINI_HOOK_COMMAND = "hornero wiki gemini hook"
GEMINI_HOOK_MATCHER = (
    "^(run_shell_command|read_file|read_many_files|grep_search|"
    "search_file_content|glob|list_directory)$"
)
GIT_HOOK_BEGIN = "# >>> hornero parrot-wiki post-commit >>>"
GIT_HOOK_END = "# <<< hornero parrot-wiki post-commit <<<"
_LEGACY_GIT_HOOK_BLOCKS = (
    (
        "# >>> parrot-wiki codex post-commit >>>",
        "# <<< parrot-wiki codex post-commit <<<",
    ),
    (
        "# >>> parrot-wiki post-commit >>>",
        "# <<< parrot-wiki post-commit <<<",
    ),
)

AGENTS_SECTION = f"""{AGENTS_BEGIN}
## Codebase Knowledge Graph (LLM Wiki)

For questions about this codebase, query the local ai-parrot knowledge graph
before scanning files:

1. Run `wikitoolkit query "<focused question>"`.
2. Open promising results with `wikitoolkit page <id>`.
3. Follow typed edges with `wikitoolkit related <id>`.
4. Use raw search only after a focused query and one page/related follow-up
   are empty. Run `wikitoolkit status` if results may be stale.

Use the `$parrot-wiki` repository skill for this workflow. Refresh large
changes with `wikitoolkit build`; post-commit upserts may already keep the
plane current. Save durable decisions and lessons with
`wikitoolkit remember "<fact>" --category decision|lesson`.
{AGENTS_END}
"""

CLAUDE_SECTION = f"""{CLAUDE_BEGIN}
## Codebase Knowledge Graph (LLM Wiki)

For questions about this codebase, query the local ai-parrot knowledge graph
before scanning files:

1. Run `wikitoolkit query "<focused question>"`.
2. Open promising results with `wikitoolkit page <id>`.
3. Follow typed edges with `wikitoolkit related <id>`.
4. Use raw search only after a focused query and one page/related follow-up
   are empty. Run `wikitoolkit status` if results may be stale.

Use the `parrot-wiki` project skill for this workflow. Refresh large changes
with `wikitoolkit build`; post-commit upserts may already keep the plane current.
Save durable decisions and lessons with
`wikitoolkit remember "<fact>" --category decision|lesson`.
{CLAUDE_END}
"""

GEMINI_SECTION = f"""{GEMINI_BEGIN}
## Codebase Knowledge Graph (LLM Wiki)

For questions about this codebase, query the local ai-parrot knowledge graph
before scanning files:

1. Run `wikitoolkit query "<focused question>"`.
2. Open promising results with `wikitoolkit page <id>`.
3. Follow typed edges with `wikitoolkit related <id>`.
4. Use raw search only after a focused query and one page/related follow-up
   are empty. Run `wikitoolkit status` if results may be stale.

Use the `parrot-wiki` workspace skill for this workflow. Refresh large changes
with `wikitoolkit build`; post-commit upserts may already keep the plane current.
Save durable decisions and lessons with
`wikitoolkit remember "<fact>" --category decision|lesson`.
{GEMINI_END}
"""

SKILL_MD = """---
name: parrot-wiki
description: Query and maintain the repository's ai-parrot LLM-wiki knowledge graph. Use for codebase questions, locating symbols or modules, understanding subsystem relationships, checking wiki health, or refreshing the local retrieval plane before raw repository scans.
---

# Parrot Wiki

Start every codebase investigation with a focused query:

1. Run `wikitoolkit query "<question>"`.
2. Read the best page with `wikitoolkit page <id>`.
3. Follow useful edges with `wikitoolkit related <id>`.
4. Answer from those results and cite page ids when practical.

If results are absent or stale, run `wikitoolkit status`; use
`wikitoolkit build` when the plane needs rebuilding. Fall back to `rg` or raw
file reads only after the query plus a page/related follow-up do not answer the
question, and state that the wiki path was exhausted.

When an investigation produces a durable fact, decision or lesson, save it
with `wikitoolkit remember "<fact>" --category <category>`. Use
`wikitoolkit note <page-id> "<note>"` for an existing page and
`wikitoolkit link <source-id> <target-id> --rel <relation>` for a typed edge.
Review authored knowledge with `wikitoolkit memories` and its provenance with
`wikitoolkit audit`.
"""

SKILL_OPENAI_YAML = """interface:
  display_name: "Parrot Wiki"
  short_description: "Query the repository knowledge graph first"
  default_prompt: "Use $parrot-wiki to answer a question from the repository knowledge graph."
"""

NUDGE_TEXT = (
    "This repository has an ai-parrot LLM-wiki. Before a raw source scan, "
    "run `wikitoolkit query \"<focused question>\"`, then inspect a result "
    "with `wikitoolkit page <id>` or `wikitoolkit related <id>`. Fall back "
    "to raw search only when that progressive-disclosure path is empty. Save "
    "durable findings with `wikitoolkit remember`."
)

_SOURCE_SUFFIXES = frozenset(
    {
        ".c", ".cc", ".cpp", ".cs", ".css", ".go", ".h", ".hpp",
        ".html", ".java", ".js", ".json", ".jsx", ".kt", ".md",
        ".php", ".py", ".rb", ".rs", ".rst", ".scala", ".sh",
        ".sql", ".swift", ".toml", ".ts", ".tsx", ".txt", ".yaml",
        ".yml",
    }
)
_SEARCH_TOOLS = frozenset(
    {"grep", "egrep", "fgrep", "rg", "ag", "ack", "ripgrep", "find"}
)
_READ_TOOLS = frozenset({"cat", "head", "tail", "sed", "awk", "bat", "less"})
_WRAPPERS = frozenset({"sudo", "command", "time", "nice", "xargs", "env"})
_SH_FAMILY = frozenset({"sh", "bash", "dash", "ash", "ksh", "ksh93", "mksh", "zsh"})


class ParrotWikiError(RuntimeError):
    """The optional ai-parrot wiki bridge could not complete an operation."""


def toolkit_available() -> bool:
    """Return whether ai-parrot's supported ``wikitoolkit`` CLI is installed."""
    return _toolkit_executable() is not None


def _toolkit_executable() -> str | None:
    """Resolve PATH first, then the current interpreter's scripts directory."""
    found = shutil.which("wikitoolkit")
    if found:
        return found
    scripts_dir = Path(sys.executable).parent
    for name in ("wikitoolkit", "wikitoolkit.exe"):
        sibling = scripts_dir / name
        if sibling.is_file():
            return str(sibling)
    return None


def _load_config(root: Path, *, create: bool = False) -> dict[str, Any]:
    path = root / CONFIG_REL
    if not path.exists():
        if not create:
            raise ParrotWikiError(f"no {CONFIG_REL}; run 'hornero wiki codex install'")
        return {
            "wiki_name": root.name,
            "storage_dir": DEFAULT_STORAGE,
            "backend": "sqlite",
            "include_suffixes": [],
            "exclude_dirs": [],
            "body_max_chars": 16_000,
            "max_file_kb": 512,
            "claude": {
                "nudge_cooldown_seconds": 60,
                "nudge_tools": ["Grep", "Glob", "Read", "Bash"],
            },
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ParrotWikiError(f"cannot parse {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ParrotWikiError(f"{path} is not a JSON object")
    return payload


def _storage_path(root: Path, config: dict[str, Any]) -> Path:
    raw = Path(str(config.get("storage_dir") or DEFAULT_STORAGE))
    return raw if raw.is_absolute() else root / raw


def wiki_built(root: Path) -> bool:
    """Check ai-parrot's persisted plane without importing ai-parrot."""
    try:
        config = _load_config(root)
    except ParrotWikiError:
        return False
    storage = _storage_path(root, config)
    if config.get("backend", "sqlite") == "memory":
        return (storage / "pages").is_dir()
    return (storage / "wiki.db").is_file()


def run_toolkit(root: Path, arguments: list[str]) -> int:
    """Run a wikitoolkit command with argv isolation and inherited output."""
    if not arguments:
        raise ParrotWikiError("a wikitoolkit command is required")
    executable = _toolkit_executable()
    if executable is None:
        raise ParrotWikiError(
            "wikitoolkit is not installed; install 'hornero[knowledge]'"
        )
    try:
        proc = subprocess.run(
            [executable, arguments[0], "--path", str(root), *arguments[1:]],
            cwd=root,
            check=False,
        )
    except OSError as exc:
        raise ParrotWikiError(f"cannot execute wikitoolkit: {exc}") from exc
    return int(proc.returncode)


def query_rows(root: Path, question: str, *, limit: int = 5) -> list[dict[str, Any]]:
    """Query ai-parrot as JSON for the generic Hornero knowledge protocol."""
    executable = _toolkit_executable()
    if executable is None:
        raise ParrotWikiError("wikitoolkit is not installed")
    try:
        proc = subprocess.run(
            [
                executable, "query", question, "--top-k", str(limit),
                "--json", "--path", str(root),
            ],
            cwd=root,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ParrotWikiError(f"wikitoolkit query failed: {exc}") from exc
    if proc.returncode:
        detail = proc.stderr.strip() or proc.stdout.strip() or "unknown error"
        raise ParrotWikiError(f"wikitoolkit query failed: {detail}")
    try:
        rows = json.loads(proc.stdout)
    except ValueError as exc:
        raise ParrotWikiError("wikitoolkit query returned invalid JSON") from exc
    if not isinstance(rows, list):
        raise ParrotWikiError("wikitoolkit query JSON is not a list")
    return [row for row in rows if isinstance(row, dict)]


def _upsert_block(text: str, block: str, begin: str, end: str) -> str:
    block = block.rstrip("\n")
    if begin in text:
        head, _, rest = text.partition(begin)
        tail = rest.partition(end)[2] if end in rest else "\n"
        return f"{head}{block}{tail}"
    if text and not text.endswith("\n"):
        text += "\n"
    separator = "\n" if text else ""
    return f"{text}{separator}{block}\n"


def _remove_block(text: str, begin: str, end: str) -> str:
    if begin not in text:
        return text
    head, _, rest = text.partition(begin)
    tail = rest.partition(end)[2] if end in rest else ""
    head = head.rstrip(" \t\n")
    if not head and not tail.strip():
        return ""
    return head + ("\n" + tail.lstrip("\n") if tail.strip() else "\n")


def _read_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ParrotWikiError(f"cannot parse {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ParrotWikiError(f"{path} is not a JSON object")
    return data


def _write_object(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _hook_entry() -> dict[str, Any]:
    return {
        "matcher": HOOK_MATCHER,
        "hooks": [{
            "type": "command",
            "command": HOOK_COMMAND,
            "timeout": 10,
            "statusMessage": "Checking repository wiki guidance",
        }],
    }


def _is_our_hook(entry: object) -> bool:
    if not isinstance(entry, dict):
        return False
    hooks = entry.get("hooks", [])
    return isinstance(hooks, list) and any(
        isinstance(hook, dict) and HOOK_COMMAND in str(hook.get("command", ""))
        for hook in hooks
    )


def _install_hooks(root: Path) -> str:
    path = root / ".codex/hooks.json"
    data = _read_object(path)
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ParrotWikiError(f"{path}: 'hooks' is not a JSON object")
    pre = hooks.setdefault("PreToolUse", [])
    if not isinstance(pre, list):
        raise ParrotWikiError(f"{path}: 'hooks.PreToolUse' is not a list")
    existing = next((entry for entry in pre if _is_our_hook(entry)), None)
    desired = _hook_entry()
    if existing == desired:
        return ".codex/hooks.json - PreToolUse hook already current"
    if isinstance(existing, dict):
        existing.clear()
        existing.update(desired)
        action = "updated"
    else:
        pre.append(desired)
        action = "added"
    _write_object(path, data)
    return f".codex/hooks.json - PreToolUse hook {action}"


def _install_agents(root: Path) -> str:
    path = root / "AGENTS.md"
    before = path.read_text(encoding="utf-8") if path.exists() else ""
    after = _upsert_block(before, AGENTS_SECTION, AGENTS_BEGIN, AGENTS_END)
    if after != before:
        path.write_text(after, encoding="utf-8")
        return "AGENTS.md - wiki guidance written"
    return "AGENTS.md - wiki guidance already current"


def _install_skill(root: Path) -> str:
    skill = root / ".agents/skills/parrot-wiki"
    targets = {
        skill / "SKILL.md": SKILL_MD,
        skill / "agents/openai.yaml": SKILL_OPENAI_YAML,
    }
    changed = False
    for path, content in targets.items():
        if not path.exists() or path.read_text(encoding="utf-8") != content:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            changed = True
    return ".agents/skills/parrot-wiki - " + ("written" if changed else "already current")


def _install_guidance(
    root: Path, filename: str, section: str, begin: str, end: str
) -> str:
    path = root / filename
    before = path.read_text(encoding="utf-8") if path.exists() else ""
    after = _upsert_block(before, section, begin, end)
    if after != before:
        path.write_text(after, encoding="utf-8")
        return f"{filename} - wiki guidance written"
    return f"{filename} - wiki guidance already current"


def _install_platform_skill(root: Path, platform: str) -> str:
    skill = root / f".{platform}/skills/parrot-wiki/SKILL.md"
    if not skill.exists() or skill.read_text(encoding="utf-8") != SKILL_MD:
        skill.parent.mkdir(parents=True, exist_ok=True)
        skill.write_text(SKILL_MD, encoding="utf-8")
        return f".{platform}/skills/parrot-wiki - written"
    return f".{platform}/skills/parrot-wiki - already current"


def _platform_hook_entry(
    *, command: str, matcher: str, timeout: int, description: str
) -> dict[str, Any]:
    return {
        "matcher": matcher,
        "hooks": [{
            "name": "parrot-wiki",
            "type": "command",
            "command": command,
            "timeout": timeout,
            "description": description,
        }],
    }


def _is_command_hook(entry: object, command: str) -> bool:
    if not isinstance(entry, dict):
        return False
    hooks = entry.get("hooks", [])
    return isinstance(hooks, list) and any(
        isinstance(hook, dict) and command in str(hook.get("command", ""))
        for hook in hooks
    )


def _install_platform_hook(
    root: Path,
    *,
    settings_rel: Path,
    event: str,
    command: str,
    matcher: str,
    timeout: int,
    description: str,
) -> str:
    path = root / settings_rel
    data = _read_object(path)
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ParrotWikiError(f"{path}: 'hooks' is not a JSON object")
    entries = hooks.setdefault(event, [])
    if not isinstance(entries, list):
        raise ParrotWikiError(f"{path}: 'hooks.{event}' is not a list")
    desired = _platform_hook_entry(
        command=command,
        matcher=matcher,
        timeout=timeout,
        description=description,
    )
    existing = next(
        (entry for entry in entries if _is_command_hook(entry, command)), None
    )
    if existing == desired:
        return f"{settings_rel} - {event} hook already current"
    if isinstance(existing, dict):
        existing.clear()
        existing.update(desired)
        action = "updated"
    else:
        entries.append(desired)
        action = "added"
    _write_object(path, data)
    return f"{settings_rel} - {event} hook {action}"


def _git_hook_path(root: Path) -> Path | None:
    git_dir = root / ".git"
    if git_dir.is_dir():
        return git_dir / "hooks/post-commit"
    if git_dir.is_file():
        try:
            value = git_dir.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        if value.startswith("gitdir:"):
            target = Path(value.split(":", 1)[1].strip())
            if not target.is_absolute():
                target = (root / target).resolve()
            common = target / "commondir"
            if common.is_file():
                target = (target / common.read_text(encoding="utf-8").strip()).resolve()
            return target / "hooks/post-commit"
    return None


def _sh_compatible(first_line: str) -> bool:
    if not first_line.startswith("#!"):
        return True
    tokens = first_line[2:].split()
    if not tokens:
        return True
    executable = PurePosixPath(tokens[0]).name
    if executable == "env" and len(tokens) > 1:
        executable = PurePosixPath(tokens[1]).name
    return executable in _SH_FAMILY


def _git_hook_block() -> str:
    return (
        f"{GIT_HOOK_BEGIN}\n"
        "# Keep the ai-parrot LLM-wiki current after each commit.\n"
        "wikitoolkit upsert --changed --quiet >/dev/null 2>&1 || true\n"
        f"{GIT_HOOK_END}\n"
    )


def _install_git_hook(root: Path) -> str:
    path = _git_hook_path(root)
    if path is None:
        return "git post-commit hook - skipped (not a git repository)"
    before = path.read_text(encoding="utf-8") if path.exists() else "#!/bin/sh\n"
    if GIT_HOOK_BEGIN in before:
        return "git post-commit hook - already installed"
    migrated = False
    for begin, end in _LEGACY_GIT_HOOK_BLOCKS:
        updated = _remove_block(before, begin, end)
        if updated != before:
            before = updated
            migrated = True
    first = before.splitlines()[0] if before.strip() else ""
    if not _sh_compatible(first):
        return "git post-commit hook - skipped (existing hook is not shell-compatible)"
    if before and not before.endswith("\n"):
        before += "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(before + _git_hook_block(), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return "git post-commit hook - " + ("migrated" if migrated else "installed")


def _install_gitignore(root: Path) -> str:
    path = root / ".gitignore"
    before = path.read_text(encoding="utf-8") if path.exists() else ""
    if any(line.strip() in {".parrot", ".parrot/", "/.parrot", "/.parrot/"}
           for line in before.splitlines()):
        return ".gitignore - .parrot already ignored"
    separator = "" if not before or before.endswith("\n") else "\n"
    path.write_text(
        before + separator + "# ai-parrot local LLM-wiki plane\n.parrot/\n",
        encoding="utf-8",
    )
    return ".gitignore - added .parrot/"


def install_codex_integration(
    root: Path, *, git_hook: bool = True, gitignore: bool = True
) -> list[str]:
    """Install idempotent Codex assets while preserving user configuration."""
    root = root.resolve()
    config_path = root / CONFIG_REL
    config = _load_config(root, create=True)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if not config_path.exists():
        _write_object(config_path, config)
        actions = [f"{CONFIG_REL} - ai-parrot project config created"]
    else:
        actions = [f"{CONFIG_REL} - existing config preserved"]
    actions.extend([_install_agents(root), _install_hooks(root), _install_skill(root)])
    if git_hook:
        actions.append(_install_git_hook(root))
    if gitignore:
        actions.append(_install_gitignore(root))
    return actions


def _ensure_project_config(root: Path) -> list[str]:
    config_path = root / CONFIG_REL
    config = _load_config(root, create=True)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if config_path.exists():
        return [f"{CONFIG_REL} - existing config preserved"]
    _write_object(config_path, config)
    return [f"{CONFIG_REL} - ai-parrot project config created"]


def install_claude_integration(
    root: Path, *, git_hook: bool = True, gitignore: bool = True
) -> list[str]:
    """Install native Claude Code instructions, skill and PreToolUse hook."""
    root = root.resolve()
    actions = _ensure_project_config(root)
    actions.extend([
        _install_guidance(
            root, "CLAUDE.md", CLAUDE_SECTION, CLAUDE_BEGIN, CLAUDE_END
        ),
        _install_platform_hook(
            root,
            settings_rel=Path(".claude/settings.json"),
            event="PreToolUse",
            command=CLAUDE_HOOK_COMMAND,
            matcher=CLAUDE_HOOK_MATCHER,
            timeout=10,
            description="Suggest the repository wiki before raw source scans",
        ),
        _install_platform_skill(root, "claude"),
    ])
    if git_hook:
        actions.append(_install_git_hook(root))
    if gitignore:
        actions.append(_install_gitignore(root))
    return actions


def install_gemini_integration(
    root: Path, *, git_hook: bool = True, gitignore: bool = True
) -> list[str]:
    """Install native Gemini CLI instructions, skill and AfterTool hook."""
    root = root.resolve()
    actions = _ensure_project_config(root)
    actions.extend([
        _install_guidance(
            root, "GEMINI.md", GEMINI_SECTION, GEMINI_BEGIN, GEMINI_END
        ),
        _install_platform_hook(
            root,
            settings_rel=Path(".gemini/settings.json"),
            event="AfterTool",
            command=GEMINI_HOOK_COMMAND,
            matcher=GEMINI_HOOK_MATCHER,
            timeout=10_000,
            description="Inject wiki guidance after a raw source scan",
        ),
        _install_platform_skill(root, "gemini"),
    ])
    if git_hook:
        actions.append(_install_git_hook(root))
    if gitignore:
        actions.append(_install_gitignore(root))
    return actions


def _remove_hook(root: Path) -> None:
    path = root / ".codex/hooks.json"
    if not path.exists():
        return
    data = _read_object(path)
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return
    pre = hooks.get("PreToolUse")
    if isinstance(pre, list):
        kept = [entry for entry in pre if not _is_our_hook(entry)]
        if kept:
            hooks["PreToolUse"] = kept
        else:
            hooks.pop("PreToolUse", None)
    if not hooks:
        data.pop("hooks", None)
    if data:
        _write_object(path, data)
    else:
        path.unlink()


def _remove_platform_hook(
    root: Path, *, settings_rel: Path, event: str, command: str
) -> None:
    path = root / settings_rel
    if not path.exists():
        return
    data = _read_object(path)
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return
    entries = hooks.get(event)
    if isinstance(entries, list):
        kept = [entry for entry in entries if not _is_command_hook(entry, command)]
        if kept:
            hooks[event] = kept
        else:
            hooks.pop(event, None)
    if not hooks:
        data.pop("hooks", None)
    if data:
        _write_object(path, data)
    else:
        path.unlink()


def _remove_guidance(root: Path, filename: str, begin: str, end: str) -> None:
    path = root / filename
    if not path.exists():
        return
    before = path.read_text(encoding="utf-8")
    after = _remove_block(before, begin, end)
    if after:
        path.write_text(after, encoding="utf-8")
    elif after != before:
        path.unlink()


def _remove_platform_skill(root: Path, platform: str) -> None:
    path = root / f".{platform}/skills/parrot-wiki/SKILL.md"
    if path.exists():
        path.unlink()
    for directory in (path.parent, path.parent.parent):
        try:
            directory.rmdir()
        except OSError:
            pass


def _has_agent_integration(root: Path) -> bool:
    candidates = (
        (root / "AGENTS.md", AGENTS_BEGIN),
        (root / "CLAUDE.md", CLAUDE_BEGIN),
        (root / "GEMINI.md", GEMINI_BEGIN),
    )
    return any(
        path.is_file() and marker in path.read_text(encoding="utf-8")
        for path, marker in candidates
    )


def _remove_git_hook(root: Path) -> None:
    path = _git_hook_path(root)
    if path is None or not path.exists():
        return
    before = path.read_text(encoding="utf-8")
    after = _remove_block(before, GIT_HOOK_BEGIN, GIT_HOOK_END)
    for begin, end in _LEGACY_GIT_HOOK_BLOCKS:
        after = _remove_block(after, begin, end)
    if after.strip() == "#!/bin/sh":
        path.unlink()
    elif after != before:
        path.write_text(after, encoding="utf-8")


def uninstall_codex_integration(root: Path) -> list[str]:
    """Remove only Hornero-managed Codex artifacts; keep config and wiki data."""
    root = root.resolve()
    agents = root / "AGENTS.md"
    if agents.exists():
        before = agents.read_text(encoding="utf-8")
        after = _remove_block(before, AGENTS_BEGIN, AGENTS_END)
        if after:
            agents.write_text(after, encoding="utf-8")
        elif after != before:
            agents.unlink()
    _remove_hook(root)
    for path in (
        root / ".agents/skills/parrot-wiki/agents/openai.yaml",
        root / ".agents/skills/parrot-wiki/SKILL.md",
    ):
        if path.exists():
            path.unlink()
    for directory in (
        root / ".agents/skills/parrot-wiki/agents",
        root / ".agents/skills/parrot-wiki",
    ):
        try:
            directory.rmdir()
        except OSError:
            pass
    if not _has_agent_integration(root):
        _remove_git_hook(root)
    return [
        "Codex wiki guidance, lifecycle hook, repository skill and git hook removed",
        f"{CONFIG_REL} and the local wiki plane were preserved",
    ]


def uninstall_claude_integration(root: Path) -> list[str]:
    """Remove only Hornero-managed Claude Code assets and keep wiki data."""
    root = root.resolve()
    _remove_guidance(root, "CLAUDE.md", CLAUDE_BEGIN, CLAUDE_END)
    _remove_platform_hook(
        root,
        settings_rel=Path(".claude/settings.json"),
        event="PreToolUse",
        command=CLAUDE_HOOK_COMMAND,
    )
    _remove_platform_skill(root, "claude")
    if not _has_agent_integration(root):
        _remove_git_hook(root)
    return [
        "Claude wiki guidance, lifecycle hook and project skill removed",
        f"{CONFIG_REL} and the local wiki plane were preserved",
    ]


def uninstall_gemini_integration(root: Path) -> list[str]:
    """Remove only Hornero-managed Gemini CLI assets and keep wiki data."""
    root = root.resolve()
    _remove_guidance(root, "GEMINI.md", GEMINI_BEGIN, GEMINI_END)
    _remove_platform_hook(
        root,
        settings_rel=Path(".gemini/settings.json"),
        event="AfterTool",
        command=GEMINI_HOOK_COMMAND,
    )
    _remove_platform_skill(root, "gemini")
    if not _has_agent_integration(root):
        _remove_git_hook(root)
    return [
        "Gemini wiki guidance, lifecycle hook and workspace skill removed",
        f"{CONFIG_REL} and the local wiki plane were preserved",
    ]


def integration_status(root: Path) -> dict[str, Any]:
    """Return machine-readable installation and runtime state."""
    hooks_path = root / ".codex/hooks.json"
    hooks_current = False
    try:
        data = _read_object(hooks_path)
        hooks = data.get("hooks", {})
        pre = hooks.get("PreToolUse", []) if isinstance(hooks, dict) else []
        hooks_current = isinstance(pre, list) and any(_is_our_hook(x) for x in pre)
    except ParrotWikiError:
        pass
    agents_path = root / "AGENTS.md"
    git_hook = _git_hook_path(root)
    return {
        "config": (root / CONFIG_REL).is_file(),
        "wiki_built": wiki_built(root),
        "wikitoolkit": toolkit_available(),
        "agents_guidance": agents_path.is_file()
        and AGENTS_BEGIN in agents_path.read_text(encoding="utf-8"),
        "pre_tool_use_hook": hooks_current,
        "repository_skill": (root / ".agents/skills/parrot-wiki/SKILL.md").is_file(),
        "git_post_commit_hook": git_hook is not None
        and git_hook.is_file()
        and GIT_HOOK_BEGIN in git_hook.read_text(encoding="utf-8"),
    }


def _platform_hook_present(
    root: Path, *, settings_rel: Path, event: str, command: str
) -> bool:
    try:
        data = _read_object(root / settings_rel)
    except ParrotWikiError:
        return False
    hooks = data.get("hooks", {})
    entries = hooks.get(event, []) if isinstance(hooks, dict) else []
    return isinstance(entries, list) and any(
        _is_command_hook(entry, command) for entry in entries
    )


def _common_status(root: Path) -> dict[str, Any]:
    git_hook = _git_hook_path(root)
    return {
        "config": (root / CONFIG_REL).is_file(),
        "wiki_built": wiki_built(root),
        "wikitoolkit": toolkit_available(),
        "git_post_commit_hook": git_hook is not None
        and git_hook.is_file()
        and GIT_HOOK_BEGIN in git_hook.read_text(encoding="utf-8"),
    }


def claude_integration_status(root: Path) -> dict[str, Any]:
    """Return machine-readable Claude Code integration state."""
    status = _common_status(root)
    guidance = root / "CLAUDE.md"
    status.update({
        "claude_guidance": guidance.is_file()
        and CLAUDE_BEGIN in guidance.read_text(encoding="utf-8"),
        "pre_tool_use_hook": _platform_hook_present(
            root,
            settings_rel=Path(".claude/settings.json"),
            event="PreToolUse",
            command=CLAUDE_HOOK_COMMAND,
        ),
        "project_skill": (root / ".claude/skills/parrot-wiki/SKILL.md").is_file(),
    })
    return status


def gemini_integration_status(root: Path) -> dict[str, Any]:
    """Return machine-readable Gemini CLI integration state."""
    status = _common_status(root)
    guidance = root / "GEMINI.md"
    status.update({
        "gemini_guidance": guidance.is_file()
        and GEMINI_BEGIN in guidance.read_text(encoding="utf-8"),
        "after_tool_hook": _platform_hook_present(
            root,
            settings_rel=Path(".gemini/settings.json"),
            event="AfterTool",
            command=GEMINI_HOOK_COMMAND,
        ),
        "workspace_skill": (root / ".gemini/skills/parrot-wiki/SKILL.md").is_file(),
    })
    return status


def _leading_executable(tokens: list[str]) -> str | None:
    for token in tokens:
        if "=" in token and not token.startswith("-") and "/" not in token.split("=", 1)[0]:
            continue
        if token in _WRAPPERS:
            continue
        return PurePosixPath(token).name
    return None


def _bash_scans_source(tool_input: dict[str, Any]) -> bool:
    command = str(tool_input.get("command") or tool_input.get("cmd") or "")
    if not command:
        return False
    for segment in re.split(r"[|&;\n]+", command):
        try:
            tokens = shlex.split(segment)
        except ValueError:
            tokens = segment.split()
        executable = _leading_executable(tokens)
        if executable in _SEARCH_TOOLS:
            return True
        if executable in _READ_TOOLS and any(
            PurePosixPath(token).suffix.lower() in _SOURCE_SUFFIXES
            for token in tokens[1:]
        ):
            return True
    return False


def _should_nudge(payload: dict[str, Any]) -> bool:
    if payload.get("hook_event_name") not in (None, "PreToolUse"):
        return False
    name = str(payload.get("tool_name") or "")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    if name == "Bash":
        return _bash_scans_source(tool_input)
    if name in {"Grep", "Glob"}:
        return True
    if name == "Read":
        target = str(tool_input.get("file_path") or tool_input.get("path") or "")
        return PurePosixPath(target).suffix.lower() in _SOURCE_SUFFIXES
    return False


def _claim_nudge(
    storage: Path, cooldown: int, now: float, *, platform: str = "codex"
) -> bool:
    if cooldown <= 0:
        return True
    bucket = int(now // cooldown)
    stamp = storage / f"{platform}_hook_nudge.{bucket}.stamp"
    try:
        storage.mkdir(parents=True, exist_ok=True)
        fd = os.open(stamp, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
    except (FileExistsError, OSError):
        return False
    for old in storage.glob(f"{platform}_hook_nudge.*.stamp"):
        if old != stamp:
            try:
                old.unlink()
            except OSError:
                pass
    return True


def build_codex_nudge(
    payload: dict[str, Any], *, root: Path | None = None, now: float | None = None
) -> dict[str, str] | None:
    """Build a non-blocking Codex PreToolUse response, or stay silent."""
    if not _should_nudge(payload):
        return None
    if root is None:
        start = Path(str(payload.get("cwd") or Path.cwd())).resolve()
        root = next(
            (candidate for candidate in (start, *start.parents)
             if (candidate / CONFIG_REL).is_file()),
            None,
        )
    if root is None or not wiki_built(root):
        return None
    try:
        config = _load_config(root)
        claude = config.get("claude", {})
        cooldown = int(claude.get("nudge_cooldown_seconds", 60)) \
            if isinstance(claude, dict) else 60
    except (ParrotWikiError, TypeError, ValueError):
        return None
    if not _claim_nudge(
        _storage_path(root, config), cooldown, time.time() if now is None else now
    ):
        return None
    # Codex PreToolUse officially supports systemMessage. It is advisory and
    # does not alter permissionDecision, so the tool call remains non-blocking.
    return {"systemMessage": NUDGE_TEXT}


def run_codex_hook(
    stdin: TextIO | None = None, stdout: TextIO | None = None
) -> int:
    """Fail-silent lifecycle-hook entry point; never break a Codex session."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    try:
        payload = json.load(stdin)
        if isinstance(payload, dict):
            response = build_codex_nudge(payload)
            if response is not None:
                json.dump(response, stdout)
                stdout.write("\n")
    except Exception:  # noqa: BLE001 - lifecycle hooks must never break sessions
        return 0
    return 0


def _input_mentions_source(value: object) -> bool:
    if isinstance(value, str):
        return PurePosixPath(value).suffix.lower() in _SOURCE_SUFFIXES
    if isinstance(value, list):
        return any(_input_mentions_source(item) for item in value)
    if isinstance(value, dict):
        return any(_input_mentions_source(item) for item in value.values())
    return False


def _should_nudge_claude(payload: dict[str, Any]) -> bool:
    if payload.get("hook_event_name") not in (None, "PreToolUse"):
        return False
    return _should_nudge({**payload, "hook_event_name": "PreToolUse"})


def _should_nudge_gemini(payload: dict[str, Any]) -> bool:
    if payload.get("hook_event_name") not in (None, "AfterTool"):
        return False
    name = str(payload.get("tool_name") or "")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    if name == "run_shell_command":
        return _bash_scans_source(tool_input)
    if name in {"grep_search", "search_file_content", "glob", "list_directory"}:
        return True
    if name in {"read_file", "read_many_files"}:
        return _input_mentions_source(tool_input)
    return False


def _agent_nudge_context(
    payload: dict[str, Any], *, root: Path | None, now: float | None, platform: str
) -> tuple[Path, dict[str, Any]] | None:
    if root is None:
        start = Path(str(payload.get("cwd") or Path.cwd())).resolve()
        root = next(
            (candidate for candidate in (start, *start.parents)
             if (candidate / CONFIG_REL).is_file()),
            None,
        )
    if root is None or not wiki_built(root):
        return None
    try:
        config = _load_config(root)
        claude = config.get("claude", {})
        cooldown = int(claude.get("nudge_cooldown_seconds", 60)) \
            if isinstance(claude, dict) else 60
    except (ParrotWikiError, TypeError, ValueError):
        return None
    if not _claim_nudge(
        _storage_path(root, config),
        cooldown,
        time.time() if now is None else now,
        platform=platform,
    ):
        return None
    return root, config


def build_claude_nudge(
    payload: dict[str, Any], *, root: Path | None = None, now: float | None = None
) -> dict[str, Any] | None:
    """Build Claude Code's non-blocking PreToolUse context response."""
    if not _should_nudge_claude(payload):
        return None
    if _agent_nudge_context(
        payload, root=root, now=now, platform="claude"
    ) is None:
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": NUDGE_TEXT,
        },
        "suppressOutput": True,
    }


def build_gemini_nudge(
    payload: dict[str, Any], *, root: Path | None = None, now: float | None = None
) -> dict[str, Any] | None:
    """Build Gemini CLI's non-blocking AfterTool context response."""
    if not _should_nudge_gemini(payload):
        return None
    if _agent_nudge_context(
        payload, root=root, now=now, platform="gemini"
    ) is None:
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "AfterTool",
            "additionalContext": NUDGE_TEXT,
        },
        "suppressOutput": True,
    }


def _run_agent_hook(
    builder: Any, stdin: TextIO | None = None, stdout: TextIO | None = None
) -> int:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    try:
        payload = json.load(stdin)
        if isinstance(payload, dict):
            response = builder(payload)
            if response is not None:
                json.dump(response, stdout)
                stdout.write("\n")
    except Exception:  # noqa: BLE001 - lifecycle hooks must never break sessions
        return 0
    return 0


def run_claude_hook(
    stdin: TextIO | None = None, stdout: TextIO | None = None
) -> int:
    """Fail-silent Claude Code hook entry point."""
    return _run_agent_hook(build_claude_nudge, stdin, stdout)


def run_gemini_hook(
    stdin: TextIO | None = None, stdout: TextIO | None = None
) -> int:
    """Fail-silent Gemini CLI hook entry point."""
    return _run_agent_hook(build_gemini_nudge, stdin, stdout)

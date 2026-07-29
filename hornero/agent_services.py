"""Grounded Hornero requests delegated to Multicoders' JSON protocol."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

from hornero.config import HorneroConfig
from hornero.lifecycle import SpecCorpus, Status
from hornero.redact import redact


class AgentServiceError(RuntimeError):
    """Grounding or provider orchestration failed closed."""


@dataclass(frozen=True, slots=True)
class GroundedContext:
    spec_id: str
    requirement: str
    evidence: tuple[dict[str, str], ...]
    constraints: tuple[dict[str, str], ...]
    product_context: str
    architecture_context: dict[str, Any] | None = None


ProtocolRunner = Callable[..., dict[str, Any]]


def collect_grounded_context(
    root: Path,
    spec_id: str,
    *,
    review_target: dict[str, str] | None = None,
    max_bytes: int = 200_000,
) -> GroundedContext:
    corpus = SpecCorpus(root / "sdd" / "specs")
    doc = corpus.by_id.get(spec_id)
    if doc is None:
        raise AgentServiceError(f"unknown spec: {spec_id}")
    remaining = max_bytes
    evidence: list[dict[str, str]] = []
    constraints: list[dict[str, str]] = []

    spec_body = _bounded(doc.body.strip(), remaining)
    remaining -= len(spec_body.encode())
    evidence.append(_evidence(f"{doc.path.relative_to(root)}#body", spec_body))
    if doc.status in {Status.APPROVED, Status.BUILDING, Status.REVIEW, Status.DONE}:
        constraints.append(
            {
                "source": f"{doc.path.relative_to(root)}#body",
                "quote": spec_body,
            }
        )

    decisions_dir = root / "sdd" / "decisions"
    if decisions_dir.is_dir():
        for path in sorted(decisions_dir.glob("*.md")):
            text = path.read_text(encoding="utf-8", errors="replace")
            if spec_id not in text or remaining <= 0:
                continue
            quote = _bounded(text.strip(), remaining)
            remaining -= len(quote.encode())
            locator = str(path.relative_to(root))
            evidence.append(_evidence(locator, quote))
            constraints.append({"source": locator, "quote": quote})

    if review_target and remaining > 0:
        diff = _review_evidence(root, review_target)
        diff = _bounded(diff, remaining)
        if diff:
            evidence.append(_evidence(_review_locator(review_target), diff))

    architecture_context = None
    from hornero.architecture.corpus import architecture_root

    if (architecture_root(root) / "project.yaml").is_file():
        from hornero.architecture.governance import (
            build_context,
            declaration_from_spec,
        )

        if declaration_from_spec(doc) is not None:
            architecture_context = build_context(root, spec_id)

    return GroundedContext(
        spec_id=spec_id,
        requirement=doc.body.strip(),
        evidence=tuple(evidence),
        constraints=tuple(constraints),
        product_context=_product_context(root),
        architecture_context=architecture_context,
    )


def build_advisory_request(
    context: GroundedContext,
    *,
    mode: str,
    question: str,
    providers: list[str],
    minimum_quorum: int,
    timeout_sec: int,
    review_target: dict[str, str] | None = None,
    autonomous: bool = False,
    resume: bool = False,
) -> dict[str, Any]:
    return {
        "protocol_version": 1,
        "mode": mode,
        "requirement": context.requirement,
        "question": question,
        "providers": providers,
        "minimum_quorum": minimum_quorum,
        "required_providers": [],
        "timeout_sec": timeout_sec,
        "autonomous": autonomous,
        "resume": resume,
        "evidence": list(context.evidence),
        "constraints": list(context.constraints),
        "architecture_context": context.architecture_context,
        "review_target": review_target or {"kind": "context", "value": ""},
    }


def build_mockup_request(
    context: GroundedContext,
    *,
    request: str,
    screenshot: Path | None,
    views: list[dict[str, str]],
    timeout_sec: int,
    visual_language: str,
    autonomous: bool = False,
    from_scratch: bool = False,
    resume: bool = False,
    parent_run_id: str | None = None,
) -> dict[str, Any]:
    return {
        "protocol_version": 1,
        "request": request,
        "screenshot": str(screenshot.resolve()) if screenshot else "",
        "views": views,
        "constraints": list(context.constraints),
        "architecture_context": context.architecture_context,
        "product_context": context.product_context,
        "visual_language": visual_language,
        "provider": "codex",
        "timeout_sec": timeout_sec,
        "autonomous": autonomous,
        "from_scratch": from_scratch,
        "resume": resume,
        "parent_run_id": parent_run_id,
    }


def invoke_multicoders(
    cfg: HorneroConfig,
    root: Path,
    subcommand: str,
    request: dict[str, Any],
    run_dir: Path,
    *,
    dry_run: bool = False,
    runner: ProtocolRunner | None = None,
) -> dict[str, Any]:
    command = resolve_multicoders_command(cfg)
    run_dir.mkdir(parents=True, exist_ok=True)
    request_path = run_dir / "request.json"
    output_path = run_dir / "result.json"
    safe_request = json.loads(redact(json.dumps(request, ensure_ascii=False)))
    for item in safe_request.get("evidence", []):
        if isinstance(item, dict) and isinstance(item.get("content"), str):
            item["sha256"] = hashlib.sha256(item["content"].encode()).hexdigest()
    request_path.write_text(
        json.dumps(safe_request, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    execute = runner or subprocess_protocol_runner
    result = execute(
        command,
        root,
        subcommand,
        request_path,
        output_path,
        cfg.multicoders.timeout_seconds,
        cfg.dispatch.max_output_bytes,
        run_dir=run_dir,
        dry_run=dry_run,
    )
    architecture_context = safe_request.get("architecture_context")
    architecture_result = result.get("architecture_result")
    if architecture_result is not None and isinstance(architecture_context, dict):
        from hornero.architecture.model import ArchitectureError
        from hornero.architecture.protocol import validate_result

        try:
            validate_result(
                architecture_result,
                expected_context_hash=str(
                    architecture_context.get("context_hash") or ""
                ),
            )
        except ArchitectureError as exc:
            raise AgentServiceError(
                f"Multicoders architecture result rejected: {exc}"
            ) from exc
    output_path.write_text(
        redact(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
        + "\n",
        encoding="utf-8",
    )
    return result


def resolve_multicoders_command(cfg: HorneroConfig) -> list[str]:
    if cfg.multicoders.command:
        return list(cfg.multicoders.command)
    executable = shutil.which("multicoders")
    if executable:
        return [executable]
    if importlib.util.find_spec("multicoders") is not None:
        return [sys.executable, "-m", "multicoders"]
    raise AgentServiceError(
        "Multicoders is not installed; configure multicoders.command or install it"
    )


def subprocess_protocol_runner(
    command: Sequence[str],
    root: Path,
    subcommand: str,
    request_path: Path,
    output_path: Path,
    timeout_seconds: float,
    max_output_bytes: int,
    *,
    run_dir: Path,
    dry_run: bool,
) -> dict[str, Any]:
    argv = [
        *command,
        subcommand,
        "--request",
        str(request_path),
        "--repo",
        str(root),
        "--output",
        str(output_path),
    ]
    if subcommand == "mockup":
        argv.extend(["--artifact-dir", str(run_dir)])
    if dry_run:
        argv.append("--dry-run")
    try:
        proc = subprocess.run(
            argv,
            cwd=root,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AgentServiceError(f"Multicoders invocation failed: {exc}") from exc
    if len(proc.stdout.encode()) + len(proc.stderr.encode()) > max_output_bytes:
        raise AgentServiceError("Multicoders output exceeded the configured limit")
    if proc.returncode not in {0, 3}:
        detail = redact((proc.stderr or proc.stdout).strip())
        raise AgentServiceError(
            f"Multicoders exited {proc.returncode}: {detail[:500]}"
        )
    if output_path.is_file():
        text = output_path.read_text(encoding="utf-8")
    else:
        text = proc.stdout
    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AgentServiceError("Multicoders returned invalid JSON") from exc
    if not isinstance(result, dict):
        raise AgentServiceError("Multicoders result must be an object")
    return result


def _review_evidence(root: Path, target: dict[str, str]) -> str:
    kind = target.get("kind", "context")
    value = target.get("value", "")
    if kind == "context":
        return ""
    if kind == "uncommitted":
        argv = ["git", "diff", "--no-ext-diff", "--binary"]
    elif kind == "base":
        if not value:
            raise AgentServiceError("base review requires a ref")
        argv = ["git", "diff", "--no-ext-diff", f"{value}...HEAD"]
    elif kind == "commit":
        if not value:
            raise AgentServiceError("commit review requires a SHA")
        argv = ["git", "show", "--format=fuller", "--no-ext-diff", value]
    else:
        raise AgentServiceError(f"unsupported review target: {kind}")
    proc = subprocess.run(
        argv,
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if proc.returncode:
        raise AgentServiceError(
            f"unable to read review target: {redact(proc.stderr.strip())}"
        )
    return proc.stdout


def _review_locator(target: dict[str, str]) -> str:
    kind = target.get("kind", "context")
    value = target.get("value", "")
    return f"git:{kind}:{value}" if value else f"git:{kind}"


def _evidence(locator: str, content: str) -> dict[str, str]:
    return {
        "locator": locator,
        "sha256": hashlib.sha256(content.encode()).hexdigest(),
        "content": content,
    }


def _bounded(text: str, remaining: int) -> str:
    if remaining <= 0:
        return ""
    encoded = text.encode()
    if len(encoded) <= remaining:
        return text
    return encoded[:remaining].decode("utf-8", "ignore")


def _product_context(root: Path) -> str:
    for name in ("README.md", "CLAUDE.md"):
        path = root / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        paragraphs = [
            paragraph.strip()
            for paragraph in text.split("\n\n")
            if paragraph.strip() and not paragraph.lstrip().startswith(("#", "!["))
        ]
        if paragraphs:
            return _bounded(paragraphs[0], 1200)
    return root.name

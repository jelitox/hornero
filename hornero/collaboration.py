"""Governed advisory and visual-artifact workflows."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

from hornero.agent_services import (
    AgentServiceError,
    ProtocolRunner,
    build_advisory_request,
    build_mockup_request,
    collect_grounded_context,
    invoke_multicoders,
)
from hornero.config import HorneroConfig
from hornero.memory.ledger import Ledger
from hornero.memory.reindex import reindex


def create_advisory(
    root: Path,
    cfg: HorneroConfig,
    *,
    spec_id: str,
    mode: str,
    question: str,
    providers: list[str] | None = None,
    minimum_quorum: int | None = None,
    review_target: dict[str, str] | None = None,
    autonomous: bool = False,
    dry_run: bool = False,
    resume: bool = False,
    runner: ProtocolRunner | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    _guard_autonomy(cfg, autonomous)
    selected = providers or cfg.multicoders.providers
    quorum = minimum_quorum or cfg.multicoders.minimum_quorum
    if quorum > len(selected):
        raise AgentServiceError("minimum quorum exceeds selected providers")
    context = collect_grounded_context(
        root,
        spec_id,
        review_target=review_target,
        max_bytes=cfg.multicoders.max_context_bytes,
    )
    with Ledger(root / ".hornero" / "ledger.db") as ledger:
        run_id = f"consult-{ledger.next_sequence('consult'):06d}"
    request = build_advisory_request(
        context,
        mode=mode,
        question=question,
        providers=selected,
        minimum_quorum=quorum,
        timeout_sec=int(cfg.multicoders.timeout_seconds),
        review_target=review_target,
        autonomous=autonomous,
        resume=resume,
    )
    run_dir = root / ".hornero" / "runs" / run_id / "advisory"
    result = invoke_multicoders(
        cfg,
        root,
        "perspective",
        request,
        run_dir,
        dry_run=dry_run,
        runner=runner,
    )
    runtime_run_id = result.get("run_id")
    if runtime_run_id and runtime_run_id != run_id:
        result["runtime_run_id"] = runtime_run_id
    result["run_id"] = run_id
    created_at = time.time() if now is None else now
    with Ledger(root / ".hornero" / "ledger.db") as ledger:
        ledger.record_advisory_run(
            run_id,
            spec_id=spec_id,
            mode=mode,
            status=str(result.get("status") or "needs_human"),
            brief_hash=(
                str(result["brief_hash"]) if result.get("brief_hash") else None
            ),
            request=request,
            result=result,
            artifact_path=str(run_dir.relative_to(root)),
            created_at=created_at,
        )
    reindex(root)
    return result


def show_advisory(root: Path, run_id: str) -> dict[str, Any] | None:
    with Ledger(root / ".hornero" / "ledger.db") as ledger:
        rows = ledger.advisory_runs(run_id)
        if not rows:
            return None
        row = rows[0]
        result = json.loads(row["result_json"])
        result["ledger_findings"] = ledger.advisory_findings(run_id)
        return result


def triage_advisory(
    root: Path,
    run_id: str,
    finding_id: str,
    disposition: str,
    reason: str,
) -> bool:
    with Ledger(root / ".hornero" / "ledger.db") as ledger:
        changed = ledger.triage_advisory_finding(
            run_id, finding_id, disposition, reason
        )
    if changed:
        reindex(root)
    return changed


def create_mockup(
    root: Path,
    cfg: HorneroConfig,
    *,
    spec_id: str,
    request_text: str,
    screenshot: Path | None,
    views: list[dict[str, str]],
    visual_language: str = "Match the attached product screenshot.",
    autonomous: bool = False,
    from_scratch: bool = False,
    dry_run: bool = False,
    resume: bool = False,
    parent_run_id: str | None = None,
    runner: ProtocolRunner | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    _guard_autonomy(cfg, autonomous)
    if len(views) > cfg.multicoders.max_views:
        raise AgentServiceError(
            f"view count exceeds configured maximum {cfg.multicoders.max_views}"
        )
    if screenshot is not None:
        screenshot = screenshot.resolve()
        if not _within(screenshot, root.resolve()):
            raise AgentServiceError("screenshot must be inside the repository")
    context = collect_grounded_context(
        root, spec_id, max_bytes=cfg.multicoders.max_context_bytes
    )
    with Ledger(root / ".hornero" / "ledger.db") as ledger:
        run_id = f"mockup-{ledger.next_sequence('mockup'):06d}"
    request = build_mockup_request(
        context,
        request=request_text,
        screenshot=screenshot,
        views=views,
        timeout_sec=int(cfg.multicoders.timeout_seconds),
        visual_language=visual_language,
        autonomous=autonomous,
        from_scratch=from_scratch,
        resume=resume,
        parent_run_id=parent_run_id,
    )
    run_dir = root / ".hornero" / "artifacts" / "mockups" / run_id
    result = invoke_multicoders(
        cfg,
        root,
        "mockup",
        request,
        run_dir,
        dry_run=dry_run,
        runner=runner,
    )
    runtime_run_id = result.get("run_id")
    if runtime_run_id and runtime_run_id != run_id:
        result["runtime_run_id"] = runtime_run_id
    result["run_id"] = run_id
    created_at = time.time() if now is None else now
    with Ledger(root / ".hornero" / "ledger.db") as ledger:
        ledger.record_mockup_run(
            run_id,
            spec_id=spec_id,
            status=str(result.get("status") or "failed"),
            provider=str(result.get("provider") or "codex"),
            parent_run_id=parent_run_id,
            manifest_path=str(
                (run_dir / "manifest.json").relative_to(root)
            ),
            request=request,
            result=result,
            created_at=created_at,
        )
    reindex(root)
    return result


def refine_mockup(
    root: Path,
    cfg: HorneroConfig,
    *,
    run_id: str,
    instruction: str,
    screenshot: Path | None = None,
    dry_run: bool = False,
    runner: ProtocolRunner | None = None,
) -> dict[str, Any]:
    with Ledger(root / ".hornero" / "ledger.db") as ledger:
        rows = ledger.mockup_runs(run_id)
    if not rows:
        raise AgentServiceError(f"unknown mockup run: {run_id}")
    prior = rows[0]
    original = json.loads(prior["request_json"])
    views = original.get("views")
    if not isinstance(views, list):
        raise AgentServiceError("previous mockup request has no views")
    request_text = (
        str(original.get("request") or "")
        + "\n\nRefinement requested: "
        + instruction.strip()
    )
    original_screenshot = str(original.get("screenshot") or "")
    selected_screenshot = screenshot or (
        Path(original_screenshot) if original_screenshot else None
    )
    return create_mockup(
        root,
        cfg,
        spec_id=str(prior["spec_id"]),
        request_text=request_text,
        screenshot=selected_screenshot,
        views=[dict(item) for item in views if isinstance(item, dict)],
        visual_language=str(original.get("visual_language") or ""),
        autonomous=bool(original.get("autonomous", False)),
        from_scratch=bool(original.get("from_scratch", False)),
        dry_run=dry_run,
        resume=True,
        parent_run_id=run_id,
        runner=runner,
    )


def show_mockup(root: Path, run_id: str) -> dict[str, Any] | None:
    with Ledger(root / ".hornero" / "ledger.db") as ledger:
        rows = ledger.mockup_runs(run_id)
        if not rows:
            return None
        result = json.loads(rows[0]["result_json"])
        result["ledger_artifacts"] = ledger.visual_artifacts(run_id)
        return result


def promote_mockup(
    root: Path,
    run_id: str,
    artifact_id: str,
    destination: Path,
) -> Path:
    root = root.resolve()
    destination = destination.resolve()
    if not _within(destination, root):
        raise AgentServiceError("promotion destination must be inside the repository")
    if destination.exists():
        raise AgentServiceError(f"promotion destination already exists: {destination}")
    with Ledger(root / ".hornero" / "ledger.db") as ledger:
        artifacts = {
            str(row["artifact_id"]): row
            for row in ledger.visual_artifacts(run_id)
        }
    artifact = artifacts.get(artifact_id)
    if artifact is None:
        raise AgentServiceError(f"unknown visual artifact: {artifact_id}")
    source = Path(str(artifact["path"])).resolve()
    if not source.is_file():
        raise AgentServiceError(f"visual artifact file is missing: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    with Ledger(root / ".hornero" / "ledger.db") as ledger:
        if not ledger.promote_visual_artifact(
            run_id, artifact_id, str(destination.relative_to(root))
        ):
            raise AgentServiceError("visual artifact promotion was not recorded")
    reindex(root)
    return destination


def _guard_autonomy(cfg: HorneroConfig, requested: bool) -> None:
    if requested and not cfg.autonomy.enabled:
        raise AgentServiceError(
            "autonomous execution is disabled in .hornero/config.yaml"
        )


def _within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents

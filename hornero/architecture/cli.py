"""CLI presentation for SPEC-013 architecture governance."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from hornero.architecture.corpus import (
    ArchitectureCorpus,
    init_architecture,
    inventory,
)
from hornero.architecture.governance import (
    architecture_diff,
    check_architecture,
    preflight_spec,
)
from hornero.architecture.model import ArchitectureError, ArchitectureReport


def _emit(value: object, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False))


def _report(report: ArchitectureReport, *, as_json: bool) -> int:
    if as_json:
        _emit(report.to_dict(), as_json=True)
    else:
        print(
            f"architecture: {report.blocking} blocking, "
            f"{report.warnings} warning(s)"
        )
        if report.profiles:
            print("profiles: " + ", ".join(report.profiles))
        for finding in report.findings:
            print(
                f"{finding.severity:<8} {finding.finding_id} "
                f"{finding.code}: {finding.message} [{finding.subject}]"
            )
    return 1 if report.blocking else 0


def run(args: Any, root: Path) -> int:
    try:
        command = args.architecture_command
        if command == "init":
            written = init_architecture(root, args.profile, project_id=args.project_id)
            init_payload: dict[str, Any] = {
                "written": [path.relative_to(root).as_posix() for path in written],
                "unchanged": not written,
            }
            if args.as_json:
                _emit(init_payload, as_json=True)
            else:
                if written:
                    for path in init_payload["written"]:
                        print(f"written: {path}")
                else:
                    print("architecture already initialized; nothing overwritten")
            return 0
        if command == "inventory":
            inventory_payload = inventory(root, propose=args.propose)
            if args.as_json:
                _emit(inventory_payload, as_json=True)
            else:
                components = inventory_payload["components"]
                languages = inventory_payload["languages"]
                assert isinstance(components, list)
                assert isinstance(languages, list)
                print(
                    f"inventory: {len(components)} component proposal(s), "
                    f"languages: {', '.join(str(item) for item in languages) or '(unknown)'}"
                )
                if inventory_payload.get("proposal_path"):
                    print(f"proposal: {inventory_payload['proposal_path']}")
            return 0

        corpus = ArchitectureCorpus(root)
        if command == "query":
            rows = [item.to_dict(root) for item in corpus.query(args.text)]
            if args.as_json:
                _emit({"results": rows}, as_json=True)
            else:
                for row in rows:
                    print(f"{row['kind']}:{row['id']} — {row['title']}")
            return 0
        if command == "explain":
            item = corpus.get(args.entity_id)
            if item is None:
                raise ArchitectureError(
                    f"unknown or ambiguous architecture entity: {args.entity_id}"
                )
            entity_payload = item.to_dict(root)
            entity_payload["raw"] = item.raw
            if args.as_json:
                _emit(entity_payload, as_json=True)
            else:
                print(f"{item.kind}:{item.record_id} — {item.title}")
                print(f"owner: {item.owner or '(missing)'}")
                print(f"authority: {item.authority.value}")
                print(f"source: {entity_payload['path']} ({item.sha256})")
            return 0
        if command == "resolve":
            if args.spec:
                from hornero import layout
                from hornero.architecture.governance import declaration_from_spec
                from hornero.lifecycle import SpecCorpus

                doc = SpecCorpus(layout.specs_dir(root)).by_id.get(args.spec)
                if doc is None:
                    raise ArchitectureError(f"unknown spec: {args.spec}")
                declaration = declaration_from_spec(doc)
                if (
                    declaration is None
                    or args.capability_id not in declaration.requests
                ):
                    raise ArchitectureError(
                        f"{args.spec} does not request capability "
                        f"{args.capability_id!r}"
                    )
            resolution_payload = corpus.resolve(args.capability_id).to_dict()
            if args.as_json:
                _emit(resolution_payload, as_json=True)
            else:
                print(
                    f"{resolution_payload['capability']}: "
                    f"{resolution_payload['resolution']}"
                    + (
                        f" -> {resolution_payload['selected']}"
                        if resolution_payload["selected"] else ""
                    )
                )
                for line in resolution_payload["explanation"]:
                    print(f"  {line}")
                for excluded in resolution_payload["excluded"]:
                    if isinstance(excluded, dict):
                        reasons = excluded.get("reasons", [])
                        print(
                            f"  excluded {excluded.get('component')}: "
                            + "; ".join(str(reason) for reason in reasons)
                        )
            return (
                1 if resolution_payload["resolution"] == "needs_human" else 0
            )
        if command == "check":
            return _report(
                check_architecture(
                    root, spec_id=args.spec, all_specs=args.all_specs
                ),
                as_json=args.as_json,
            )
        if command == "diff":
            git_ref = args.base or args.commit
            delta_payload = architecture_diff(
                root, spec_id=args.spec, git_ref=git_ref,
                commit=bool(args.commit),
            )
            if args.as_json:
                _emit(delta_payload, as_json=True)
            else:
                print(
                    f"architecture delta: "
                    f"{len(delta_payload['deviations'])} deviation(s)"
                )
                for item in delta_payload["deviations"]:
                    print(f"{item['kind']}: {item['entity']} — {item['message']}")
            return 1 if delta_payload["deviations"] else 0
        if command == "exception":
            exceptions = corpus.list("exception")
            if args.exception_command == "list":
                exception_payloads = [item.to_dict(root) for item in exceptions]
                if args.as_json:
                    _emit({"exceptions": exception_payloads}, as_json=True)
                else:
                    for exception_payload in exception_payloads:
                        print(
                            f"{exception_payload['id']} — "
                            f"{exception_payload['status']}"
                        )
                return 0
            item = corpus.get(args.exception_id, "exception")
            if item is None:
                raise ArchitectureError(f"unknown exception: {args.exception_id}")
            exception_payload = item.to_dict(root)
            exception_payload["raw"] = item.raw
            if args.as_json:
                _emit(exception_payload, as_json=True)
            else:
                print(f"{item.record_id} — {item.title}")
                print(json.dumps(item.raw, indent=2, sort_keys=True))
            return 0
        raise AssertionError("unknown architecture command")
    except ArchitectureError as exc:
        print(f"architecture error: {exc}", file=sys.stderr)
        return 2


def run_spec(args: Any, root: Path) -> int:
    try:
        report = preflight_spec(root, args.spec_id)
    except ArchitectureError as exc:
        print(f"architecture error: {exc}", file=sys.stderr)
        return 2
    return _report(report, as_json=args.as_json)

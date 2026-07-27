"""Operational ledger: SQLite at ``.hornero/ledger.db`` (SPEC-001 §4).

The audit backbone: runs, deltas (DUPLICATEs included — persisted, never
dispatched), dropped drafts (``evidence_mismatch`` et al.), dispatch results
with PR URLs, and checkpoints. Gitignored operational state, not knowledge.

Determinism: every write takes explicit timestamps from the caller; nothing
in here reads the wall clock.
"""

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 7

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id      TEXT PRIMARY KEY,
    command     TEXT NOT NULL,
    started_at  REAL NOT NULL,
    finished_at REAL,
    dry_run     INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS deltas (
    delta_id     TEXT PRIMARY KEY,
    run_id       TEXT NOT NULL,
    kind         TEXT NOT NULL,
    title        TEXT NOT NULL,
    status       TEXT NOT NULL,
    confidence   REAL NOT NULL,
    payload_json TEXT NOT NULL,
    decision     TEXT,
    outcome      TEXT,
    presented_count INTEGER NOT NULL DEFAULT 0,
    last_presented_run TEXT
);
CREATE TABLE IF NOT EXISTS dropped_drafts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       TEXT NOT NULL,
    reason       TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at   REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS verdicts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    delta_id     TEXT NOT NULL,
    judge        TEXT NOT NULL,
    vote         TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dispatches (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    spec_id    TEXT NOT NULL,
    run_id     TEXT NOT NULL,
    status     TEXT NOT NULL,
    pr_url     TEXT,
    branch     TEXT,
    trace_path TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_runs (
    run_ref     TEXT PRIMARY KEY,
    spec_id     TEXT,
    task_id     TEXT,
    actor       TEXT NOT NULL,
    status      TEXT NOT NULL,
    trace_path  TEXT NOT NULL,
    started_at  REAL NOT NULL,
    finished_at REAL
);
CREATE TABLE IF NOT EXISTS checkpoints (
    key        TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS sequences (
    name       TEXT PRIMARY KEY,
    next_value INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS improvement_runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       TEXT NOT NULL,
    finding_id   TEXT NOT NULL,
    status       TEXT NOT NULL,
    branch       TEXT,
    details_json TEXT NOT NULL,
    created_at   REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS graph_snapshots (
    snapshot_id  TEXT PRIMARY KEY,
    head_ref     TEXT,
    manifest_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS graph_entity_versions (
    entity_id     TEXT NOT NULL,
    version_hash  TEXT NOT NULL,
    kind          TEXT NOT NULL,
    payload_json  TEXT NOT NULL,
    first_snapshot TEXT NOT NULL,
    last_snapshot  TEXT NOT NULL,
    active         INTEGER NOT NULL,
    PRIMARY KEY (entity_id, version_hash)
);
CREATE INDEX IF NOT EXISTS idx_graph_versions_entity
ON graph_entity_versions(entity_id, active);
CREATE TABLE IF NOT EXISTS runtime_events (
    event_id       TEXT PRIMARY KEY,
    action         TEXT NOT NULL,
    payload_json   TEXT NOT NULL,
    risk           TEXT NOT NULL,
    cost_units     INTEGER NOT NULL,
    status         TEXT NOT NULL,
    attempts       INTEGER NOT NULL DEFAULT 0,
    next_at        REAL NOT NULL,
    created_at     REAL NOT NULL,
    result_json    TEXT,
    approved_by    TEXT
);
CREATE INDEX IF NOT EXISTS idx_runtime_events_ready
ON runtime_events(status, next_at);
CREATE TABLE IF NOT EXISTS runtime_schedules (
    schedule_id TEXT PRIMARY KEY,
    last_at     REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS runtime_feedback (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id  TEXT NOT NULL,
    rule_id     TEXT NOT NULL,
    rating      INTEGER NOT NULL,
    notes       TEXT NOT NULL,
    created_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS runtime_webhooks (
    delivery_id TEXT PRIMARY KEY,
    event_id    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS advisory_runs (
    run_id       TEXT PRIMARY KEY,
    spec_id      TEXT NOT NULL,
    mode         TEXT NOT NULL,
    status       TEXT NOT NULL,
    brief_hash   TEXT,
    request_json TEXT NOT NULL,
    result_json  TEXT NOT NULL,
    artifact_path TEXT NOT NULL,
    created_at   REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS advisory_findings (
    finding_id   TEXT PRIMARY KEY,
    run_id       TEXT NOT NULL,
    provider     TEXT NOT NULL,
    summary      TEXT NOT NULL,
    severity     TEXT NOT NULL,
    disposition  TEXT NOT NULL,
    reason       TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_advisory_findings_run
ON advisory_findings(run_id);
CREATE TABLE IF NOT EXISTS mockup_runs (
    run_id       TEXT PRIMARY KEY,
    spec_id      TEXT NOT NULL,
    status       TEXT NOT NULL,
    provider     TEXT NOT NULL,
    parent_run_id TEXT,
    manifest_path TEXT NOT NULL,
    request_json TEXT NOT NULL,
    result_json  TEXT NOT NULL,
    created_at   REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS visual_artifacts (
    artifact_id  TEXT PRIMARY KEY,
    run_id       TEXT NOT NULL,
    view_name    TEXT NOT NULL,
    path         TEXT NOT NULL,
    sha256       TEXT NOT NULL,
    media_type   TEXT NOT NULL,
    width        INTEGER NOT NULL,
    height       INTEGER NOT NULL,
    bytes        INTEGER NOT NULL,
    promoted_path TEXT
);
CREATE INDEX IF NOT EXISTS idx_visual_artifacts_run
ON visual_artifacts(run_id);
"""


def _enable_wal(connection: sqlite3.Connection) -> None:
    """Enable WAL despite concurrent first-open races on a new database."""
    for attempt in range(10):
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            return
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt == 9:
                raise
            time.sleep(0.01 * (attempt + 1))


class Ledger:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, timeout=30)
        self._conn.row_factory = sqlite3.Row
        _enable_wal(self._conn)
        self._conn.executescript(_SCHEMA)
        columns = {
            str(row["name"])
            for row in self._conn.execute("PRAGMA table_info(deltas)")
        }
        if "decision" not in columns:
            self._conn.execute("ALTER TABLE deltas ADD COLUMN decision TEXT")
        if "outcome" not in columns:
            self._conn.execute("ALTER TABLE deltas ADD COLUMN outcome TEXT")
        if "presented_count" not in columns:
            self._conn.execute(
                "ALTER TABLE deltas ADD COLUMN presented_count INTEGER "
                "NOT NULL DEFAULT 0"
            )
        if "last_presented_run" not in columns:
            self._conn.execute(
                "ALTER TABLE deltas ADD COLUMN last_presented_run TEXT"
            )
        first_run = self._conn.execute(
            "SELECT COALESCE(MAX(CAST(SUBSTR(run_id, 3) AS INTEGER)), 0) + 1 "
            "FROM runs WHERE run_id GLOB 'r-[0-9]*'"
        ).fetchone()[0]
        self._conn.execute(
            "INSERT OR IGNORE INTO sequences (name, next_value) VALUES ('run', ?)",
            (first_run,),
        )
        self._conn.execute(
            "INSERT OR IGNORE INTO checkpoints (key, value_json, updated_at) "
            "VALUES ('schema_version', ?, 0)",
            (json.dumps(SCHEMA_VERSION),),
        )
        self._conn.execute(
            "UPDATE checkpoints SET value_json = ? WHERE key = 'schema_version'",
            (json.dumps(SCHEMA_VERSION),),
        )
        self._conn.commit()

    # -- lifecycle ---------------------------------------------------------
    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Ledger":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- writes ------------------------------------------------------------
    def record_run(
        self, run_id: str, command: str, started_at: float, *, dry_run: bool = False
    ) -> None:
        self._conn.execute(
            "INSERT INTO runs (run_id, command, started_at, dry_run) VALUES (?,?,?,?)",
            (run_id, command, started_at, int(dry_run)),
        )
        if run_id.startswith("r-") and run_id[2:].isdigit():
            self._conn.execute(
                "UPDATE sequences SET next_value = MAX(next_value, ?) "
                "WHERE name = 'run'",
                (int(run_id[2:]) + 1,),
            )
        self._conn.commit()

    def finish_run(self, run_id: str, finished_at: float) -> None:
        self._conn.execute(
            "UPDATE runs SET finished_at = ? WHERE run_id = ?", (finished_at, run_id)
        )
        self._conn.commit()

    def record_delta(
        self,
        delta_id: str,
        run_id: str,
        kind: str,
        title: str,
        status: str,
        confidence: float,
        payload: dict[str, Any],
        *,
        decision: str | None = None,
        outcome: str | None = None,
    ) -> None:
        self._conn.execute(
            "INSERT INTO deltas "
            "(delta_id, run_id, kind, title, status, confidence, payload_json, "
            "decision, outcome) VALUES (?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(delta_id) DO UPDATE SET "
            "run_id=excluded.run_id, kind=excluded.kind, title=excluded.title, "
            "status=excluded.status, confidence=excluded.confidence, "
            "payload_json=excluded.payload_json, decision=excluded.decision, "
            "outcome=excluded.outcome",
            (
                delta_id, run_id, kind, title, status, confidence,
                json.dumps(payload), decision, outcome,
            ),
        )
        self._conn.commit()

    def mark_delta_presented(self, delta_id: str, run_id: str) -> None:
        self._conn.execute(
            "UPDATE deltas SET presented_count = presented_count + 1, "
            "last_presented_run = ? WHERE delta_id = ?",
            (run_id, delta_id),
        )
        self._conn.commit()

    def record_dropped_draft(
        self, run_id: str, reason: str, payload: dict[str, Any], created_at: float
    ) -> None:
        self._conn.execute(
            "INSERT INTO dropped_drafts (run_id, reason, payload_json, created_at) "
            "VALUES (?,?,?,?)",
            (run_id, reason, json.dumps(payload), created_at),
        )
        self._conn.commit()

    def record_verdict(
        self, delta_id: str, judge: str, vote: str, payload: dict[str, Any]
    ) -> None:
        self._conn.execute(
            "INSERT INTO verdicts (delta_id, judge, vote, payload_json) VALUES (?,?,?,?)",
            (delta_id, judge, vote, json.dumps(payload)),
        )
        self._conn.commit()

    def record_dispatch(
        self,
        spec_id: str,
        run_id: str,
        status: str,
        pr_url: str | None,
        branch: str | None,
        trace_path: str,
        created_at: float,
    ) -> None:
        self._conn.execute(
            "INSERT INTO dispatches "
            "(spec_id, run_id, status, pr_url, branch, trace_path, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (spec_id, run_id, status, pr_url, branch, trace_path, created_at),
        )
        self._conn.commit()

    def record_agent_run(
        self,
        run_ref: str,
        *,
        spec_id: str | None,
        task_id: str | None,
        actor: str,
        status: str,
        trace_path: str,
        started_at: float,
        finished_at: float | None = None,
    ) -> None:
        """SPEC-004 §3.3: the join point between specs, tasks and traces."""
        self._conn.execute(
            "INSERT OR REPLACE INTO agent_runs "
            "(run_ref, spec_id, task_id, actor, status, trace_path, "
            "started_at, finished_at) VALUES (?,?,?,?,?,?,?,?)",
            (run_ref, spec_id, task_id, actor, status, trace_path,
             started_at, finished_at),
        )
        self._conn.commit()

    def record_improvement(
        self, run_id: str, finding_id: str, status: str,
        branch: str | None, details: dict[str, Any], created_at: float,
    ) -> None:
        self._conn.execute(
            "INSERT INTO improvement_runs "
            "(run_id, finding_id, status, branch, details_json, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (run_id, finding_id, status, branch, json.dumps(details), created_at),
        )
        self._conn.commit()

    def record_advisory_run(
        self,
        run_id: str,
        *,
        spec_id: str,
        mode: str,
        status: str,
        brief_hash: str | None,
        request: dict[str, Any],
        result: dict[str, Any],
        artifact_path: str,
        created_at: float,
    ) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO advisory_runs "
            "(run_id, spec_id, mode, status, brief_hash, request_json, "
            "result_json, artifact_path, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                run_id, spec_id, mode, status, brief_hash,
                json.dumps(request, sort_keys=True, ensure_ascii=False),
                json.dumps(result, sort_keys=True, ensure_ascii=False),
                artifact_path, created_at,
            ),
        )
        synthesis = result.get("synthesis", {})
        findings = synthesis.get("findings", []) if isinstance(synthesis, dict) else []
        if isinstance(findings, list):
            for raw in findings:
                if not isinstance(raw, dict) or not raw.get("finding_id"):
                    continue
                self._conn.execute(
                    "INSERT OR REPLACE INTO advisory_findings "
                    "(finding_id, run_id, provider, summary, severity, "
                    "disposition, reason, payload_json) VALUES (?,?,?,?,?,?,?,?)",
                    (
                        str(raw["finding_id"]), run_id,
                        str(raw.get("provider") or ""),
                        str(raw.get("summary") or ""),
                        str(raw.get("severity") or "unknown"),
                        str(raw.get("disposition") or "ESCALATE"),
                        str(raw.get("disposition_reason") or ""),
                        json.dumps(raw, sort_keys=True, ensure_ascii=False),
                    ),
                )
        self._conn.commit()

    def advisory_runs(self, run_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM advisory_runs"
        args: tuple[Any, ...] = ()
        if run_id is not None:
            query += " WHERE run_id=?"
            args = (run_id,)
        rows = self._conn.execute(query + " ORDER BY created_at, run_id", args)
        return [dict(row) for row in rows]

    def advisory_findings(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM advisory_findings WHERE run_id=? ORDER BY finding_id",
            (run_id,),
        )
        return [dict(row) for row in rows]

    def triage_advisory_finding(
        self,
        run_id: str,
        finding_id: str,
        disposition: str,
        reason: str,
    ) -> bool:
        if disposition not in {"CONFIRM", "REJECT", "ESCALATE"}:
            raise ValueError(f"invalid disposition: {disposition}")
        if not reason.strip():
            raise ValueError("triage reason must not be empty")
        row = self._conn.execute(
            "SELECT payload_json FROM advisory_findings "
            "WHERE run_id=? AND finding_id=?",
            (run_id, finding_id),
        ).fetchone()
        if row is None:
            return False
        payload = json.loads(row["payload_json"])
        payload["disposition"] = disposition
        payload["disposition_reason"] = reason.strip()
        self._conn.execute(
            "UPDATE advisory_findings SET disposition=?, reason=?, payload_json=? "
            "WHERE run_id=? AND finding_id=?",
            (
                disposition, reason.strip(),
                json.dumps(payload, sort_keys=True, ensure_ascii=False),
                run_id, finding_id,
            ),
        )
        run = self._conn.execute(
            "SELECT result_json FROM advisory_runs WHERE run_id=?", (run_id,)
        ).fetchone()
        if run is not None:
            result = json.loads(run["result_json"])
            findings = result.get("synthesis", {}).get("findings", [])
            for finding in findings:
                if isinstance(finding, dict) and finding.get("finding_id") == finding_id:
                    finding["disposition"] = disposition
                    finding["disposition_reason"] = reason.strip()
            self._conn.execute(
                "UPDATE advisory_runs SET result_json=? WHERE run_id=?",
                (
                    json.dumps(result, sort_keys=True, ensure_ascii=False),
                    run_id,
                ),
            )
        self._conn.commit()
        return True

    def record_mockup_run(
        self,
        run_id: str,
        *,
        spec_id: str,
        status: str,
        provider: str,
        parent_run_id: str | None,
        manifest_path: str,
        request: dict[str, Any],
        result: dict[str, Any],
        created_at: float,
    ) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO mockup_runs "
            "(run_id, spec_id, status, provider, parent_run_id, manifest_path, "
            "request_json, result_json, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                run_id, spec_id, status, provider, parent_run_id, manifest_path,
                json.dumps(request, sort_keys=True, ensure_ascii=False),
                json.dumps(result, sort_keys=True, ensure_ascii=False),
                created_at,
            ),
        )
        artifacts = result.get("artifacts", [])
        if isinstance(artifacts, list):
            for raw in artifacts:
                if not isinstance(raw, dict):
                    continue
                digest = str(raw.get("sha256") or "")
                view_name = str(raw.get("view") or "")
                if not digest or not view_name:
                    continue
                artifact_id = f"visual-{digest[:20]}"
                self._conn.execute(
                    "INSERT OR REPLACE INTO visual_artifacts "
                    "(artifact_id, run_id, view_name, path, sha256, media_type, "
                    "width, height, bytes, promoted_path) VALUES (?,?,?,?,?,?,?,?,?,"
                    "COALESCE((SELECT promoted_path FROM visual_artifacts "
                    "WHERE artifact_id=?), NULL))",
                    (
                        artifact_id, run_id, view_name, str(raw.get("path") or ""),
                        digest, str(raw.get("media_type") or "image/png"),
                        int(raw.get("width") or 0), int(raw.get("height") or 0),
                        int(raw.get("bytes") or 0), artifact_id,
                    ),
                )
        self._conn.commit()

    def mockup_runs(self, run_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM mockup_runs"
        args: tuple[Any, ...] = ()
        if run_id is not None:
            query += " WHERE run_id=?"
            args = (run_id,)
        rows = self._conn.execute(query + " ORDER BY created_at, run_id", args)
        return [dict(row) for row in rows]

    def visual_artifacts(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM visual_artifacts WHERE run_id=? ORDER BY view_name",
            (run_id,),
        )
        return [dict(row) for row in rows]

    def promote_visual_artifact(
        self, run_id: str, artifact_id: str, promoted_path: str,
    ) -> bool:
        cursor = self._conn.execute(
            "UPDATE visual_artifacts SET promoted_path=? "
            "WHERE run_id=? AND artifact_id=?",
            (promoted_path, run_id, artifact_id),
        )
        self._conn.commit()
        return cursor.rowcount == 1

    def improvements(self, finding_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM improvement_runs"
        args: tuple[Any, ...] = ()
        if finding_id is not None:
            query += " WHERE finding_id = ?"
            args = (finding_id,)
        rows = self._conn.execute(query + " ORDER BY id", args)
        return [dict(row) for row in rows]

    def record_graph_snapshot(
        self, snapshot_id: str, head_ref: str | None, manifest_hash: str,
        entities: list[tuple[str, str, str, dict[str, Any]]],
    ) -> bool:
        """Record immutable entity versions; repeated snapshots are no-ops."""
        exists = self._conn.execute(
            "SELECT 1 FROM graph_snapshots WHERE snapshot_id = ?", (snapshot_id,)
        ).fetchone()
        if exists:
            return False
        current_ids = {entity_id for entity_id, _, _, _ in entities}
        active = self._conn.execute(
            "SELECT entity_id, version_hash FROM graph_entity_versions "
            "WHERE active = 1"
        ).fetchall()
        for row in active:
            if str(row["entity_id"]) not in current_ids:
                self._conn.execute(
                    "UPDATE graph_entity_versions SET active=0, last_snapshot=? "
                    "WHERE entity_id=? AND version_hash=?",
                    (snapshot_id, row["entity_id"], row["version_hash"]),
                )
        for entity_id, kind, version_hash, payload in entities:
            self._conn.execute(
                "UPDATE graph_entity_versions SET active=0, last_snapshot=? "
                "WHERE entity_id=? AND version_hash<>? AND active=1",
                (snapshot_id, entity_id, version_hash),
            )
            self._conn.execute(
                "INSERT INTO graph_entity_versions "
                "(entity_id, version_hash, kind, payload_json, first_snapshot, "
                "last_snapshot, active) VALUES (?,?,?,?,?,?,1) "
                "ON CONFLICT(entity_id, version_hash) DO UPDATE SET "
                "last_snapshot=excluded.last_snapshot, active=1",
                (
                    entity_id, version_hash, kind,
                    json.dumps(payload, sort_keys=True, ensure_ascii=False),
                    snapshot_id, snapshot_id,
                ),
            )
        self._conn.execute(
            "INSERT INTO graph_snapshots VALUES (?,?,?)",
            (snapshot_id, head_ref, manifest_hash),
        )
        self._conn.commit()
        return True

    def graph_history(self, entity_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM graph_entity_versions WHERE entity_id=? "
            "ORDER BY first_snapshot, version_hash", (entity_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    def graph_snapshots(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM graph_snapshots ORDER BY snapshot_id"
        ).fetchall()
        return [dict(row) for row in rows]

    def next_sequence(self, name: str) -> int:
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            self._conn.execute(
                "INSERT OR IGNORE INTO sequences (name, next_value) VALUES (?, 1)",
                (name,),
            )
            row = self._conn.execute(
                "SELECT next_value FROM sequences WHERE name=?", (name,)
            ).fetchone()
            assert row is not None
            value = int(row["next_value"])
            self._conn.execute(
                "UPDATE sequences SET next_value=? WHERE name=?", (value + 1, name)
            )
            self._conn.commit()
            return value
        except Exception:
            self._conn.rollback()
            raise

    def emit_runtime_event(
        self, action: str, payload: dict[str, Any], risk: str, cost_units: int,
        now: float,
    ) -> str:
        event_id = f"evt-{self.next_sequence('runtime-event')}"
        self._conn.execute(
            "INSERT INTO runtime_events "
            "(event_id, action, payload_json, risk, cost_units, status, next_at, "
            "created_at) VALUES (?,?,?,?,?,'queued',?,?)",
            (event_id, action, json.dumps(payload), risk, cost_units, now, now),
        )
        self._conn.commit()
        return event_id

    def emit_webhook_event(
        self, delivery_id: str, action: str, payload: dict[str, Any],
        risk: str, cost_units: int, now: float,
    ) -> tuple[str, bool]:
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            existing = self._conn.execute(
                "SELECT event_id FROM runtime_webhooks WHERE delivery_id=?",
                (delivery_id,),
            ).fetchone()
            if existing:
                self._conn.commit()
                return str(existing["event_id"]), False
            self._conn.execute(
                "INSERT OR IGNORE INTO sequences (name, next_value) "
                "VALUES ('runtime-event', 1)"
            )
            row = self._conn.execute(
                "SELECT next_value FROM sequences WHERE name='runtime-event'"
            ).fetchone()
            assert row is not None
            value = int(row["next_value"])
            self._conn.execute(
                "UPDATE sequences SET next_value=? WHERE name='runtime-event'",
                (value + 1,),
            )
            event_id = f"evt-{value}"
            self._conn.execute(
                "INSERT INTO runtime_events "
                "(event_id, action, payload_json, risk, cost_units, status, "
                "next_at, created_at) VALUES (?,?,?,?,?,'queued',?,?)",
                (event_id, action, json.dumps(payload), risk, cost_units, now, now),
            )
            self._conn.execute(
                "INSERT INTO runtime_webhooks VALUES (?,?)", (delivery_id, event_id)
            )
            self._conn.commit()
            return event_id, True
        except Exception:
            self._conn.rollback()
            raise

    def runtime_events(self, *, ready_at: float | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM runtime_events"
        args: tuple[Any, ...] = ()
        if ready_at is not None:
            query += " WHERE status IN ('queued','retry','awaiting_approval') AND next_at<=?"
            args = (ready_at,)
        rows = self._conn.execute(query + " ORDER BY created_at, event_id", args)
        return [dict(row) for row in rows]

    def update_runtime_event(
        self, event_id: str, *, status: str, attempts: int,
        next_at: float, result: dict[str, Any] | None = None,
        approved_by: str | None = None,
    ) -> None:
        self._conn.execute(
            "UPDATE runtime_events SET status=?, attempts=?, next_at=?, "
            "result_json=?, approved_by=COALESCE(?, approved_by) WHERE event_id=?",
            (
                status, attempts, next_at,
                json.dumps(result, sort_keys=True) if result is not None else None,
                approved_by, event_id,
            ),
        )
        self._conn.commit()

    def schedule_due(self, schedule_id: str, now: float, every_seconds: float) -> bool:
        row = self._conn.execute(
            "SELECT last_at FROM runtime_schedules WHERE schedule_id=?", (schedule_id,)
        ).fetchone()
        return row is None or now - float(row["last_at"]) >= every_seconds

    def mark_schedule(self, schedule_id: str, now: float) -> None:
        self._conn.execute(
            "INSERT INTO runtime_schedules VALUES (?,?) ON CONFLICT(schedule_id) "
            "DO UPDATE SET last_at=excluded.last_at", (schedule_id, now),
        )
        self._conn.commit()

    def record_feedback(
        self, finding_id: str, rule_id: str, rating: int, notes: str, now: float,
    ) -> None:
        if rating not in (-1, 1):
            raise ValueError("feedback rating must be -1 or 1")
        self._conn.execute(
            "INSERT INTO runtime_feedback "
            "(finding_id, rule_id, rating, notes, created_at) VALUES (?,?,?,?,?)",
            (finding_id, rule_id, rating, notes, now),
        )
        self._conn.commit()

    def policy_weights(self) -> dict[str, float]:
        rows = self._conn.execute(
            "SELECT rule_id, SUM(CASE WHEN rating=1 THEN 1 ELSE 0 END) positive, "
            "SUM(CASE WHEN rating=-1 THEN 1 ELSE 0 END) negative "
            "FROM runtime_feedback GROUP BY rule_id ORDER BY rule_id"
        ).fetchall()
        return {
            str(row["rule_id"]): max(
                0.5, min(1.5, (float(row["positive"]) + 1) / (float(row["negative"]) + 1))
            )
            for row in rows
        }

    def runtime_metrics(self) -> dict[str, Any]:
        statuses = {
            str(row["status"]): int(row["n"])
            for row in self._conn.execute(
                "SELECT status, COUNT(*) n FROM runtime_events GROUP BY status"
            )
        }
        totals = self._conn.execute(
            "SELECT COUNT(*) n, COALESCE(SUM(cost_units),0) cost, "
            "COALESCE(SUM(attempts),0) attempts FROM runtime_events"
        ).fetchone()
        return {
            "events": int(totals["n"]), "cost_units": int(totals["cost"]),
            "attempts": int(totals["attempts"]), "by_status": statuses,
            "policy_weights": self.policy_weights(),
        }

    def agent_runs(self, spec_id: str | None = None) -> list[dict[str, Any]]:
        q = "SELECT * FROM agent_runs"
        args: tuple = ()
        if spec_id is not None:
            q += " WHERE spec_id = ?"
            args = (spec_id,)
        rows = self._conn.execute(q + " ORDER BY run_ref", args).fetchall()
        return [dict(r) for r in rows]

    def checkpoint_set(self, key: str, value: Any, updated_at: float) -> None:
        self._conn.execute(
            "INSERT INTO checkpoints (key, value_json, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, "
            "updated_at=excluded.updated_at",
            (key, json.dumps(value), updated_at),
        )
        self._conn.commit()

    # -- reads -------------------------------------------------------------
    def checkpoint_get(self, key: str) -> Any:
        row = self._conn.execute(
            "SELECT value_json FROM checkpoints WHERE key = ?", (key,)
        ).fetchone()
        return json.loads(row["value_json"]) if row else None

    def dropped_drafts(self, run_id: str | None = None) -> list[dict[str, Any]]:
        q = "SELECT * FROM dropped_drafts"
        args: tuple[Any, ...] = ()
        if run_id is not None:
            q += " WHERE run_id = ?"
            args = (run_id,)
        return [dict(r) for r in self._conn.execute(q + " ORDER BY id", args)]

    def queued_deltas(self) -> list[dict[str, Any]]:
        """SPEC-003 §7 U2: deltas parked past the per-signal budget, waiting
        for the next reconcile run."""
        rows = self._conn.execute(
            "SELECT * FROM deltas WHERE status='queued' ORDER BY delta_id"
        ).fetchall()
        return [dict(r) for r in rows]

    def deltas(self, run_id: str | None = None) -> list[dict[str, Any]]:
        q = "SELECT * FROM deltas"
        args: tuple[Any, ...] = ()
        if run_id is not None:
            q += " WHERE run_id = ?"
            args = (run_id,)
        return [dict(r) for r in self._conn.execute(q + " ORDER BY delta_id", args)]

    def dispatches(self, spec_id: str | None = None) -> list[dict[str, Any]]:
        q = "SELECT * FROM dispatches"
        args: tuple[Any, ...] = ()
        if spec_id is not None:
            q += " WHERE spec_id = ?"
            args = (spec_id,)
        return [dict(r) for r in self._conn.execute(q + " ORDER BY id", args)]

    def next_run_id(self) -> str:
        """Atomically reserve a monotonic run id: r-1, r-2, ..."""
        value = self.next_sequence("run")
        return f"r-{value}"

    def trace(self, spec_id: str) -> dict[str, list[dict[str, Any]]]:
        """The signal → delta → spec → PR chain for one spec (§11
        traceability): deltas that touched it plus its dispatches."""
        touching = []
        for row in self.deltas():
            payload = json.loads(row["payload_json"])
            affected = payload.get("affected_specs", [])
            if spec_id in affected or payload.get("created_spec") == spec_id:
                touching.append(row)
        return {"deltas": touching, "dispatches": self.dispatches(spec_id)}

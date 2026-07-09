"""Operational ledger: SQLite at ``.hornero/ledger.db`` (SPEC-001 §4).

The audit backbone: runs, deltas (DUPLICATEs included — persisted, never
dispatched), dropped drafts (``evidence_mismatch`` et al.), dispatch results
with PR URLs, and checkpoints. Gitignored operational state, not knowledge.

Determinism: every write takes explicit timestamps from the caller; nothing
in here reads the wall clock.
"""

import json
import sqlite3
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

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
    payload_json TEXT NOT NULL
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
    log_path   TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS checkpoints (
    key        TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at REAL NOT NULL
);
"""


class Ledger:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.execute(
            "INSERT OR IGNORE INTO checkpoints (key, value_json, updated_at) "
            "VALUES ('schema_version', ?, 0)",
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
    ) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO deltas "
            "(delta_id, run_id, kind, title, status, confidence, payload_json) "
            "VALUES (?,?,?,?,?,?,?)",
            (delta_id, run_id, kind, title, status, confidence, json.dumps(payload)),
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
        log_path: str,
        created_at: float,
    ) -> None:
        self._conn.execute(
            "INSERT INTO dispatches "
            "(spec_id, run_id, status, pr_url, branch, log_path, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (spec_id, run_id, status, pr_url, branch, log_path, created_at),
        )
        self._conn.commit()

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
        """Deterministic monotonic run id: r-1, r-2, ..."""
        n = self._conn.execute("SELECT COUNT(*) AS c FROM runs").fetchone()["c"]
        return f"r-{n + 1}"

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

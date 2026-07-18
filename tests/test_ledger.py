"""Ledger schema, append, trace, and idempotency tests."""

from concurrent.futures import ThreadPoolExecutor

from hornero.memory.ledger import SCHEMA_VERSION, Ledger


def test_schema_idempotent(tmp_path):
    db = tmp_path / "ledger.db"
    with Ledger(db):
        pass
    with Ledger(db) as second:  # re-open: no failure, no duplication
        assert second.checkpoint_get("schema_version") == SCHEMA_VERSION


def test_record_and_query_dropped_draft(tmp_path):
    with Ledger(tmp_path / "l.db") as led:
        led.record_run("r-1", "reconcile", 100.0, dry_run=True)
        led.record_dropped_draft(
            "r-1", "evidence_mismatch", {"title": "ghost"}, 101.0
        )
        rows = led.dropped_drafts("r-1")
        assert len(rows) == 1
        assert rows[0]["reason"] == "evidence_mismatch"
        assert '"ghost"' in rows[0]["payload_json"]


def test_record_dispatch_and_trace(tmp_path):
    with Ledger(tmp_path / "l.db") as led:
        led.record_run("r-1", "reconcile", 100.0)
        led.record_delta(
            "dlt-r-1-1", "r-1", "changed", "t", "approved", 0.9,
            {"affected_specs": ["SPEC-002"]},
        )
        led.record_delta(
            "dlt-r-1-2", "r-1", "new", "t2", "approved", 0.8,
            {"affected_specs": [], "created_spec": "SPEC-003"},
        )
        led.record_dispatch(
            "SPEC-002", "r-2", "completed",
            "https://example.invalid/pr/1", "hornero/SPEC-002", "/log", 200.0,
        )
        chain = led.trace("SPEC-002")
        assert [d["delta_id"] for d in chain["deltas"]] == ["dlt-r-1-1"]
        assert chain["dispatches"][0]["pr_url"] == "https://example.invalid/pr/1"
        # created_spec linkage
        assert [d["delta_id"] for d in led.trace("SPEC-003")["deltas"]] == ["dlt-r-1-2"]


def test_checkpoint_upsert(tmp_path):
    with Ledger(tmp_path / "l.db") as led:
        led.checkpoint_set("k", {"a": 1}, 1.0)
        led.checkpoint_set("k", {"a": 2}, 2.0)
        assert led.checkpoint_get("k") == {"a": 2}
        assert led.checkpoint_get("missing") is None


def test_next_run_id_monotonic(tmp_path):
    with Ledger(tmp_path / "l.db") as led:
        assert led.next_run_id() == "r-1"
        led.record_run("r-1", "reconcile", 1.0)
        assert led.next_run_id() == "r-2"


def test_next_run_id_is_unique_across_concurrent_connections(tmp_path):
    for attempt in range(3):
        db = tmp_path / f"l-{attempt}.db"

        def reserve(_, database=db):
            with Ledger(database) as led:
                return led.next_run_id()

        with ThreadPoolExecutor(max_workers=8) as pool:
            ids = list(pool.map(reserve, range(24)))
        assert len(ids) == len(set(ids)) == 24
        assert {int(value.removeprefix("r-")) for value in ids} == set(range(1, 25))


def test_delta_decision_and_outcome_are_distinct(tmp_path):
    with Ledger(tmp_path / "l.db") as led:
        led.record_delta(
            "d-1", "r-1", "changed", "x", "failed", 0.8, {},
            decision="approved", outcome="failed",
        )
        row = led.deltas()[0]
        assert row["decision"] == "approved"
        assert row["outcome"] == "failed"


def test_run_finish_and_dry_run_flag(tmp_path):
    with Ledger(tmp_path / "l.db") as led:
        led.record_run("r-1", "reconcile", 1.0, dry_run=True)
        led.finish_run("r-1", 2.0)
        row = led._conn.execute("SELECT * FROM runs").fetchone()
        assert row["dry_run"] == 1 and row["finished_at"] == 2.0

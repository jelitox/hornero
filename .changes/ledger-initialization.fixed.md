Retry SQLite WAL activation during concurrent first-open races so deterministic
ledger tests and parallel CLI starts do not fail with a transient database lock.

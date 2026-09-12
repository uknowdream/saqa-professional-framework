"""Safe, isolated SQLite quality gate for database-layer regression checks.

The gate uses an in-memory database only. It validates schema constraints,
foreign-key enforcement, parameterized access, aggregation, and rollback.
No external database or persistent data is touched.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path


def _expect_integrity_error(conn: sqlite3.Connection, sql: str, params: tuple[object, ...], message: str) -> None:
    try:
        conn.execute(sql, params)
    except sqlite3.IntegrityError:
        conn.rollback()
    else:
        conn.rollback()
        raise AssertionError(message)


def run() -> dict[str, object]:
    started = time.perf_counter()
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        fk_enabled = conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert fk_enabled
        conn.executescript(
            """
            CREATE TABLE teams (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE
            );
            CREATE TABLE test_runs (
                id INTEGER PRIMARY KEY,
                team_id INTEGER NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('PASS','FAIL','BLOCKED','UNVERIFIED')),
                duration_ms REAL NOT NULL CHECK(duration_ms >= 0),
                FOREIGN KEY(team_id) REFERENCES teams(id)
            );
            """
        )
        conn.execute("INSERT INTO teams(id, name) VALUES (?, ?)", (1, "SAQA"))
        _expect_integrity_error(
            conn,
            "INSERT INTO teams(id, name) VALUES (?, ?)",
            (2, "SAQA"),
            "UNIQUE constraint was not rejected",
        )
        _expect_integrity_error(
            conn,
            "INSERT INTO test_runs(team_id, status, duration_ms) VALUES (?, ?, ?)",
            (1, None, 1),
            "NOT NULL constraint was not rejected",
        )
        conn.executemany(
            "INSERT INTO test_runs(team_id, status, duration_ms) VALUES (?, ?, ?)",
            [(1, "PASS", 120.5), (1, "PASS", 140.0), (1, "FAIL", 310.25)],
        )
        row = conn.execute(
            "SELECT COUNT(*), SUM(duration_ms), AVG(duration_ms) FROM test_runs WHERE team_id = ?",
            (1,),
        ).fetchone()
        assert row == (3, 570.75, 190.25)

        _expect_integrity_error(
            conn,
            "INSERT INTO test_runs(team_id, status, duration_ms) VALUES (?, ?, ?)",
            (999, "PASS", 1),
            "foreign-key violation was not rejected",
        )
        _expect_integrity_error(
            conn,
            "INSERT INTO test_runs(team_id, status, duration_ms) VALUES (?, ?, ?)",
            (1, "INVALID", 1),
            "CHECK constraint was not rejected",
        )
        _expect_integrity_error(
            conn,
            "INSERT INTO test_runs(team_id, status, duration_ms) VALUES (?, ?, ?)",
            (1, "PASS", -1),
            "duration CHECK constraint was not rejected",
        )

        before = conn.execute("SELECT COUNT(*) FROM test_runs").fetchone()[0]
        try:
            with conn:
                conn.execute(
                    "INSERT INTO test_runs(team_id, status, duration_ms) VALUES (?, ?, ?)",
                    (1, "PASS", 50),
                )
                raise RuntimeError("intentional rollback probe")
        except RuntimeError:
            pass
        after = conn.execute("SELECT COUNT(*) FROM test_runs").fetchone()[0]
        assert before == after

        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        evidence: dict[str, object] = {
            "schema": "saqa.database-quality.v1",
            "test_id": "database.isolated-sqlite-quality-gate",
            "status": "PASS",
            "target": "sqlite::memory:",
            "http_methods": [],
            "destructive_actions": False,
            "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "details": {
                "foreign_keys": True,
                "parameterized_queries": True,
                "constraint_checks": True,
                "aggregation": True,
                "transaction_rollback": True,
                "duration_ms": elapsed_ms,
            },
        }
    finally:
        conn.close()

    output = Path("artifacts/targets/database-quality.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    return evidence


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=2))

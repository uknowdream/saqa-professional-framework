"""Safe, isolated SQLite quality gate for database-layer regression checks."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path


def _expect_integrity_error(conn: sqlite3.Connection, sql: str, params: tuple[object, ...], message: str) -> None:
    conn.execute("SAVEPOINT constraint_probe")
    try:
        conn.execute(sql, params)
    except sqlite3.IntegrityError:
        conn.execute("ROLLBACK TO constraint_probe")
        conn.execute("RELEASE constraint_probe")
    else:
        conn.execute("ROLLBACK TO constraint_probe")
        conn.execute("RELEASE constraint_probe")
        raise AssertionError(message)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run() -> dict[str, object]:
    started = time.perf_counter()
    output = Path("artifacts/targets/database-quality.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    evidence: dict[str, object] = {
        "schema": "saqa.database-quality.v2", "test_id": "database.isolated-sqlite-quality-gate",
        "status": "UNVERIFIED", "target": "sqlite::memory:", "http_methods": [],
        "destructive_actions": False, "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "details": {},
    }
    conn = None
    try:
        conn = sqlite3.connect(":memory:")
        conn.execute("PRAGMA foreign_keys = ON")
        fk_enabled = conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        _require(fk_enabled, "foreign-key enforcement is disabled")
        conn.executescript("""
            CREATE TABLE teams (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
            CREATE TABLE test_runs (
                id INTEGER PRIMARY KEY, team_id INTEGER NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('PASS','FAIL','BLOCKED','UNVERIFIED')),
                duration_ms REAL NOT NULL CHECK(duration_ms >= 0),
                FOREIGN KEY(team_id) REFERENCES teams(id)
            );
        """)
        conn.execute("INSERT INTO teams(id, name) VALUES (?, ?)", (1, "SAQA"))
        _expect_integrity_error(conn, "INSERT INTO teams(id, name) VALUES (?, ?)", (1, "duplicate-id"), "PRIMARY KEY constraint was not rejected")
        _expect_integrity_error(conn, "INSERT INTO teams(id, name) VALUES (?, ?)", (2, "SAQA"), "UNIQUE constraint was not rejected")
        _expect_integrity_error(conn, "INSERT INTO test_runs(team_id, status, duration_ms) VALUES (?, ?, ?)", (1, None, 1), "NOT NULL constraint was not rejected")
        conn.executemany("INSERT INTO test_runs(team_id, status, duration_ms) VALUES (?, ?, ?)", [(1, "PASS", 120.5), (1, "PASS", 140.0), (1, "FAIL", 310.25)])
        row = conn.execute("SELECT COUNT(*), SUM(duration_ms), AVG(duration_ms) FROM test_runs WHERE team_id = ?", (1,)).fetchone()
        _require(row == (3, 570.75, 190.25), f"unexpected aggregation result: {row!r}")
        _expect_integrity_error(conn, "INSERT INTO test_runs(team_id, status, duration_ms) VALUES (?, ?, ?)", (999, "PASS", 1), "foreign-key violation was not rejected")
        _expect_integrity_error(conn, "INSERT INTO test_runs(team_id, status, duration_ms) VALUES (?, ?, ?)", (1, "INVALID", 1), "CHECK constraint was not rejected")
        _expect_integrity_error(conn, "INSERT INTO test_runs(team_id, status, duration_ms) VALUES (?, ?, ?)", (1, "PASS", -1), "duration CHECK constraint was not rejected")
        conn.commit()
        before = conn.execute("SELECT COUNT(*) FROM test_runs").fetchone()[0]
        try:
            with conn:
                conn.execute("INSERT INTO test_runs(team_id, status, duration_ms) VALUES (?, ?, ?)", (1, "PASS", 50))
                raise RuntimeError("intentional rollback probe")
        except RuntimeError:
            pass
        after = conn.execute("SELECT COUNT(*) FROM test_runs").fetchone()[0]
        _require(before == after, "transaction rollback probe did not restore row count")
        evidence["status"] = "PASS"
        evidence["details"] = {"foreign_keys": True, "primary_key_constraint": True, "unique_constraint": True, "parameterized_queries": True, "constraint_checks": True, "aggregation": True, "transaction_rollback": True, "duration_ms": round((time.perf_counter() - started) * 1000, 2)}
    except Exception as exc:
        evidence["status"] = "FAIL"
        evidence["details"] = {"error": f"{type(exc).__name__}: {exc}", "duration_ms": round((time.perf_counter() - started) * 1000, 2)}
    finally:
        if conn is not None:
            conn.close()
        output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    return evidence


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))

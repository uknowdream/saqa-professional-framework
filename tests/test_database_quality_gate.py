import sqlite3

from scripts.database_quality_gate import _expect_integrity_error, run


def test_constraint_probe_preserves_prior_transaction_state():
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("CREATE TABLE teams (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL)")
        conn.execute("INSERT INTO teams(id, name) VALUES (?, ?)", (1, "SAQA"))
        _expect_integrity_error(
            conn,
            "INSERT INTO teams(id, name) VALUES (?, ?)",
            (2, "SAQA"),
            "UNIQUE constraint was not rejected",
        )
        assert conn.execute("SELECT COUNT(*) FROM teams").fetchone()[0] == 1
        assert conn.execute("SELECT name FROM teams WHERE id = ?", (1,)).fetchone()[0] == "SAQA"
    finally:
        conn.close()


def test_database_quality_gate_passes_and_emits_safe_evidence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    evidence = run()
    assert evidence["status"] == "PASS"
    assert evidence["target"] == "sqlite::memory:"
    assert evidence["destructive_actions"] is False
    details = evidence["details"]
    assert details["foreign_keys"] is True
    assert details["parameterized_queries"] is True
    assert details["constraint_checks"] is True
    assert details["transaction_rollback"] is True

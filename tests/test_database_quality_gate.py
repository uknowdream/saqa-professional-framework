from scripts.database_quality_gate import run


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

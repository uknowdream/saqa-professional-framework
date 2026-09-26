import json
from pathlib import Path
import httpx
import pytest
from saqa.allure import write_allure_results
from saqa.evidence import EvidenceRecord
from saqa.history import append_history, verify_history
from saqa.property_testing import deterministic_cases, assert_read_only_request, exercise_contract_cases
from saqa.resilience import retry_read_only

def record(status="PASS", details=None):
    return EvidenceRecord("QE-1", status, "2026-09-27T00:00:00+00:00", "http://127.0.0.1:3000", details or {"metric":42})

def test_allure_result_is_commit_bound_and_retains_details(tmp_path: Path):
    assert write_allure_results([record(), record("FAIL")], tmp_path, commit_sha="abc") == 2
    results = sorted(tmp_path.glob("*-result.json"))
    assert len(results) == 2
    for result_file in results:
        data = json.loads(result_file.read_text())
        labels = {item["name"]: item["value"] for item in data["labels"]}
        assert labels["commit"] == "abc"
        assert labels["target"] == "http://127.0.0.1:3000"
        assert data["historyId"]
        assert data["start"] == 1790467200000
        assert data["attachments"]

def test_history_is_append_only_and_tamper_evident(tmp_path: Path):
    path = tmp_path/"history.jsonl"
    append_history([record()], path, commit_sha="a")
    append_history([record("FAIL")], path, commit_sha="b")
    entries = [json.loads(line) for line in path.read_text().splitlines()]
    assert [entry["commit_sha"] for entry in entries] == ["a","b"]
    assert entries[1]["previous_sha256"] == entries[0]["chain_sha256"]
    assert verify_history(path)
    entries[0]["records"][0]["status"] = "FAIL"
    lines = path.read_text().splitlines()
    lines[0] = json.dumps(entries[0])
    path.write_text("\n".join(lines) + "\n")
    assert not verify_history(path)

def test_history_rejects_corrupted_chain_on_append(tmp_path: Path):
    path = tmp_path/"history.jsonl"
    append_history([record()], path, commit_sha="a")
    path.write_text(path.read_text().replace('"commit_sha": "a"', '"commit_sha": "tampered"'))
    with pytest.raises(RuntimeError, match="corrupted"):
        append_history([record()], path, commit_sha="b")

def test_history_malformed_line_returns_false(tmp_path: Path):
    path = tmp_path/"history.jsonl"
    path.write_text("{not-json}\n")
    assert not verify_history(path)

def test_property_cases_are_deterministic():
    assert deterministic_cases() == deterministic_cases()
    assert len(deterministic_cases(count=40)) == 40

def test_property_suite_rejects_non_read_only_or_non_loopback():
    with pytest.raises(AssertionError): assert_read_only_request("POST","http://127.0.0.1:3000")
    with pytest.raises(AssertionError): assert_read_only_request("GET","https://example.com")
    with pytest.raises(AssertionError): assert_read_only_request("GET","http://127.0.0.1:3000@evil.example")
    with pytest.raises(AssertionError): assert_read_only_request("GET","http://user:pass@127.0.0.1:3000")

def test_property_executor_is_fail_closed():
    result = exercise_contract_cases([{"q":"a"},{"q":""}], lambda case:(200,"application/json"))
    assert result["passed"] == 2
    with pytest.raises(AssertionError):
        exercise_contract_cases([{"q":"bad"}], lambda case:(500,"text/html"))

def test_retry_succeeds_after_transient_timeout():
    calls={"n":0}
    def op():
        calls["n"] += 1
        if calls["n"] < 3: raise TimeoutError("transient")
        return "ok"
    assert retry_read_only(op, attempts=3) == ("ok",3)

def test_retry_handles_httpx_timeout():
    calls={"n":0}
    def op():
        calls["n"] += 1
        if calls["n"] < 2: raise httpx.ReadTimeout("transient")
        return "ok"
    assert retry_read_only(op, attempts=2) == ("ok",2)

def test_retry_does_not_swallow_unexpected_error():
    with pytest.raises(ValueError):
        retry_read_only(lambda: (_ for _ in ()).throw(ValueError("bad")), attempts=3)

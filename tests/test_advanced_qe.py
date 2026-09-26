import json
from pathlib import Path
import pytest
from saqa.allure import write_allure_results
from saqa.evidence import EvidenceRecord
from saqa.history import append_history, verify_history
from saqa.property_testing import deterministic_cases, assert_read_only_request, exercise_contract_cases
from saqa.resilience import retry_read_only

def record(status="PASS"):
    return EvidenceRecord("QE-1",status,"2026-09-27T00:00:00+00:00","http://127.0.0.1:3000",{})

def test_allure_result_is_commit_bound(tmp_path:Path):
    assert write_allure_results([record()],tmp_path,commit_sha="abc")==1
    data=json.loads(next(tmp_path.glob("*-result.json")).read_text())
    assert {"commit","target"} <= {x["name"] for x in data["labels"]}
    assert data["historyId"]

def test_history_is_append_only_and_tamper_evident(tmp_path:Path):
    path=tmp_path/"history.jsonl"
    append_history([record()],path,commit_sha="a")
    append_history([record("FAIL")],path,commit_sha="b")
    assert verify_history(path)
    lines=path.read_text().splitlines()
    first=json.loads(lines[0]); first["records"][0]["status"]="FAIL"
    lines[0]=json.dumps(first)
    path.write_text("\n".join(lines)+"\n")
    assert not verify_history(path)

def test_property_cases_are_deterministic():
    assert deterministic_cases()==deterministic_cases()
    assert len(deterministic_cases(count=40))==40

def test_property_suite_rejects_non_read_only_or_non_loopback():
    with pytest.raises(AssertionError): assert_read_only_request("POST","http://127.0.0.1:3000")
    with pytest.raises(AssertionError): assert_read_only_request("GET","https://example.com")

def test_property_executor_is_fail_closed():
    result=exercise_contract_cases([{"q":"a"},{"q":""}],lambda case:(200,"application/json"))
    assert result["passed"]==2

def test_retry_succeeds_after_transient_timeout():
    calls={"n":0}
    def op():
        calls["n"]+=1
        if calls["n"]<3: raise TimeoutError("transient")
        return "ok"
    assert retry_read_only(op,attempts=3)==("ok",3)

def test_retry_does_not_swallow_unexpected_error():
    with pytest.raises(ValueError):
        retry_read_only(lambda: (_ for _ in ()).throw(ValueError("bad")),attempts=3)

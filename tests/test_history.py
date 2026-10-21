import json
from saqa.history import append_history, verify_history
from saqa.evidence import EvidenceRecord

def test_history_chain_is_valid_and_ordered(tmp_path):
    path=tmp_path/"history.jsonl"
    r=EvidenceRecord("A","PASS","2026-09-27T00:00:00+00:00","http://127.0.0.1:3000",{"x":1})
    append_history([r],path,commit_sha="a")
    append_history([r],path,commit_sha="b")
    assert verify_history(path)
    entries=[json.loads(x) for x in path.read_text().splitlines()]
    assert entries[1]["previous_sha256"]==entries[0]["chain_sha256"]


def test_history_with_noncanonical_nan_payload_is_invalid(tmp_path):
    from saqa.history import GENESIS

    path = tmp_path / "history.jsonl"
    entry = {
        "commit_sha": "abc",
        "records": [{"score": float("nan")}],
        "previous_sha256": GENESIS,
        "chain_sha256": "0" * 64,
    }
    # Python JSON accepts NaN by default; canonical evidence JSON intentionally does not.
    path.write_text(json.dumps(entry) + "\\n", encoding="utf-8")
    assert verify_history(path) is False


def test_deeply_nested_history_line_is_invalid(tmp_path):
    path = tmp_path / "history.jsonl"
    path.write_text("[" * 2000 + "0" + "]" * 2000 + "\\n", encoding="utf-8")
    assert verify_history(path) is False

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

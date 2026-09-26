"""Allure-compatible result generation from canonical SAQA evidence."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
from .evidence import EvidenceRecord

_STATUS_TO_ALLURE={"PASS":0,"FAIL":1,"BLOCKED":2,"UNVERIFIED":3,"NOT_APPLICABLE":4}

def write_allure_results(records:list[EvidenceRecord], output_dir:Path, *, commit_sha:str)->int:
    output_dir.mkdir(parents=True,exist_ok=True)
    written=0
    for record in records:
        uid=hashlib.sha256(f"{commit_sha}:{record.test_id}:{record.observed_at}".encode()).hexdigest()
        payload={
            "uuid":uid,"historyId":hashlib.sha256(record.test_id.encode()).hexdigest(),
            "name":record.test_id,"fullName":record.test_id,
            "status": {"PASS":"passed","FAIL":"failed","BLOCKED":"broken","UNVERIFIED":"unknown","NOT_APPLICABLE":"skipped"}[record.status],
            "statusDetails":{"message":record.status},
            "start":0,"stop":0,
            "labels":[{"name":"target","value":record.target},{"name":"commit","value":commit_sha}],
            "parameters":[{"name":"status","value":record.status}],
        }
        (output_dir/f"{uid}-result.json").write_text(json.dumps(payload,sort_keys=True,indent=2)+"\n",encoding="utf-8")
        written+=1
    return written

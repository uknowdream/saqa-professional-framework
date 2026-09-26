"""Append-only, hash-chained quality history for deterministic trend analysis."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
from .evidence import canonical_json,EvidenceRecord

GENESIS="0"*64

def append_history(records:list[EvidenceRecord], path:Path, *, commit_sha:str)->str:
    path.parent.mkdir(parents=True,exist_ok=True)
    previous=GENESIS
    if path.exists():
        lines=[x for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
        if lines:
            previous=json.loads(lines[-1])["chain_sha256"]
    entry={"commit_sha":commit_sha,"records":[r.__dict__ for r in records],"previous_sha256":previous}
    entry["chain_sha256"]=hashlib.sha256(canonical_json(entry)).hexdigest()
    with path.open("a",encoding="utf-8") as handle:
        handle.write(json.dumps(entry,sort_keys=True)+"\n")
    return entry["chain_sha256"]

def verify_history(path:Path)->bool:
    if not path.exists(): return False
    previous=GENESIS
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip(): continue
        entry=json.loads(line)
        digest=entry.pop("chain_sha256",None)
        if entry.get("previous_sha256")!=previous: return False
        if not isinstance(digest,str): return False
        if hashlib.sha256(canonical_json(entry)).hexdigest()!=digest: return False
        previous=digest
    return previous!=GENESIS

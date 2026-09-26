"""Append-only, hash-chained quality history for deterministic trend analysis."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
from .evidence import EvidenceRecord, canonical_json

GENESIS = "0" * 64

def _verify_lines(lines: list[str]) -> bool:
    previous = GENESIS
    saw_entry = False
    for line in lines:
        if not line.strip():
            continue
        saw_entry = True
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            return False
        if not isinstance(entry, dict):
            return False
        digest = entry.get("chain_sha256")
        if not isinstance(digest, str) or entry.get("previous_sha256") != previous:
            return False
        unsigned = dict(entry)
        unsigned.pop("chain_sha256", None)
        if hashlib.sha256(canonical_json(unsigned)).hexdigest() != digest:
            return False
        previous = digest
    return saw_entry

def verify_history(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        return _verify_lines(path.read_text(encoding="utf-8").splitlines())
    except (OSError, UnicodeError):
        return False

def append_history(records: list[EvidenceRecord], path: Path, *, commit_sha: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    lock_path.touch(exist_ok=True)
    try:
        import fcntl
    except ImportError:
        fcntl = None
    handle = lock_path.open("r+", encoding="utf-8")
    try:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        previous = GENESIS
        if path.exists() and path.stat().st_size:
            if not verify_history(path):
                raise RuntimeError("cannot append to corrupted quality history")
            lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
            previous = json.loads(lines[-1])["chain_sha256"]
        entry = {"commit_sha": commit_sha, "records": [r.__dict__ for r in records], "previous_sha256": previous}
        entry["chain_sha256"] = hashlib.sha256(canonical_json(entry)).hexdigest()
        with path.open("a", encoding="utf-8") as output:
            output.write(json.dumps(entry, sort_keys=True) + "\n")
        return entry["chain_sha256"]
    finally:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()

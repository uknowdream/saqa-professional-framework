"""Tamper-evident evidence primitives for SAQA."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

STATUSES = {"PASS", "FAIL", "BLOCKED", "UNVERIFIED", "NOT_APPLICABLE"}

@dataclass(frozen=True)
class EvidenceRecord:
    test_id: str
    status: str
    observed_at: str
    target: str
    details: dict

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"invalid status: {self.status}")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(records: list[EvidenceRecord], output: Path) -> str:
    payload = [asdict(record) for record in records]
    digest = hashlib.sha256(canonical_json(payload)).hexdigest()
    output.write_text(json.dumps({"records": payload, "sha256": digest}, indent=2), encoding="utf-8")
    return digest


def verify_manifest(path: Path) -> bool:
    data = json.loads(path.read_text(encoding="utf-8"))
    expected = data.get("sha256")
    records = data.get("records")
    if not isinstance(expected, str) or not isinstance(records, list):
        return False
    actual = hashlib.sha256(canonical_json(records)).hexdigest()
    return actual == expected

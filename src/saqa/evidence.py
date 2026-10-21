"""Tamper-evident evidence primitives for SAQA."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATUSES = {"PASS", "FAIL", "BLOCKED", "UNVERIFIED", "NOT_APPLICABLE"}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED_RECORD_FIELDS = {"test_id", "status", "observed_at", "target", "details"}


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
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(records: list[EvidenceRecord], output: Path) -> str:
    payload = [asdict(record) for record in records]
    digest = hashlib.sha256(canonical_json(payload)).hexdigest()
    output.write_text(json.dumps({"records": payload, "sha256": digest}, indent=2, allow_nan=False), encoding="utf-8")
    return digest


def _valid_record(record: Any) -> bool:
    if not isinstance(record, dict) or not _REQUIRED_RECORD_FIELDS.issubset(record):
        return False
    if not isinstance(record["test_id"], str) or not record["test_id"].strip():
        return False
    if not isinstance(record["status"], str) or record["status"] not in STATUSES:
        return False
    if not isinstance(record["observed_at"], str) or not record["observed_at"].strip():
        return False
    if not isinstance(record["target"], str) or not record["target"].strip():
        return False
    if not isinstance(record["details"], dict):
        return False
    return True


def verify_manifest(path: Path) -> bool:
    """Return False for malformed, structurally invalid, or tampered manifests."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError):
        return False
    if not isinstance(data, dict):
        return False
    expected = data.get("sha256")
    records = data.get("records")
    if not isinstance(expected, str) or not _SHA256_RE.fullmatch(expected):
        return False
    if not isinstance(records, list) or not records or not all(_valid_record(record) for record in records):
        return False
    try:
        actual = hashlib.sha256(canonical_json(records)).hexdigest()
    except (TypeError, ValueError, OverflowError):
        return False
    return actual == expected

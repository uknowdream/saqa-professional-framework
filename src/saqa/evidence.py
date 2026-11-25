"""Tamper-evident SHA-256 and optional HMAC-SHA256 signed evidence primitives for SAQA."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
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
        if not isinstance(self.test_id, str) or not self.test_id.strip():
            raise ValueError("test_id must be a non-empty string")
        if not isinstance(self.status, str) or self.status not in STATUSES:
            raise ValueError(f"invalid status: {self.status}")
        if not isinstance(self.observed_at, str) or not self.observed_at.strip():
            raise ValueError("observed_at must be a non-empty string")
        if not isinstance(self.target, str) or not self.target.strip():
            raise ValueError("target must be a non-empty string")
        if not isinstance(self.details, dict):
            raise ValueError("details must be an object")


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


def compute_hmac_sha256(canonical_payload: bytes, signing_key: str) -> str:
    """Compute cryptographic HMAC-SHA256 provenance signature over canonical evidence bytes."""
    if not signing_key:
        raise ValueError("signing_key must be non-empty")
    return hmac.new(signing_key.encode("utf-8"), canonical_payload, hashlib.sha256).hexdigest()


def write_manifest(
    records: list[EvidenceRecord],
    output: Path,
    *,
    signing_key: str | None = None,
) -> str:
    if not records:
        raise ValueError("evidence manifest requires at least one record")
    payload = [asdict(record) for record in records]
    canonical_bytes = canonical_json(payload)
    digest = hashlib.sha256(canonical_bytes).hexdigest()
    manifest_doc: dict[str, Any] = {"records": payload, "sha256": digest}
    active_key = signing_key if signing_key is not None else os.getenv("SAQA_EVIDENCE_SIGNING_KEY", "")
    if active_key:
        manifest_doc["hmac_sha256"] = compute_hmac_sha256(canonical_bytes, active_key)
    output.write_text(json.dumps(manifest_doc, indent=2, allow_nan=False), encoding="utf-8")
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


def verify_manifest(path: Path, *, signing_key: str | None = None, require_signature: bool = False) -> bool:
    """Return False for malformed, structurally invalid, tampered, or bad-signature manifests."""
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
        canonical_bytes = canonical_json(records)
        actual = hashlib.sha256(canonical_bytes).hexdigest()
    except (TypeError, ValueError, OverflowError):
        return False
    if actual != expected:
        return False

    active_key = signing_key if signing_key is not None else os.getenv("SAQA_EVIDENCE_SIGNING_KEY", "")
    recorded_hmac = data.get("hmac_sha256")
    if require_signature and (not active_key or not isinstance(recorded_hmac, str)):
        return False
    if active_key and recorded_hmac is not None:
        if not isinstance(recorded_hmac, str) or not _SHA256_RE.fullmatch(recorded_hmac):
            return False
        expected_hmac = compute_hmac_sha256(canonical_bytes, active_key)
        if not hmac.compare_digest(recorded_hmac, expected_hmac):
            return False
    return True

"""Strict certification gates: unknown or incomplete evidence never becomes PASS."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .evidence import EvidenceRecord

ALLOWED_STATUSES = frozenset({"PASS", "FAIL", "BLOCKED", "UNVERIFIED", "NOT_APPLICABLE"})


@dataclass(frozen=True)
class CertificationResult:
    status: str
    total: int
    counts: dict[str, int]
    reason: str


def certify(records: list[EvidenceRecord], required_total: int | None = None) -> CertificationResult:
    counts = Counter(record.status for record in records)
    total = len(records)
    unknown = set(counts) - ALLOWED_STATUSES
    if unknown:
        return CertificationResult("FAIL", total, dict(counts), "unknown evidence status cannot be certified")
    if required_total is not None and total != required_total:
        return CertificationResult("FAIL", total, dict(counts), "evidence count does not match required test count")
    if not records:
        return CertificationResult("UNVERIFIED", 0, {}, "no evidence records")
    if counts.get("FAIL", 0):
        return CertificationResult("FAIL", total, dict(counts), "one or more executed tests failed")
    if counts.get("BLOCKED", 0) or counts.get("UNVERIFIED", 0):
        return CertificationResult("UNVERIFIED", total, dict(counts), "incomplete evidence cannot be certified")
    return CertificationResult("PASS", total, dict(counts), "all applicable evidence passed")

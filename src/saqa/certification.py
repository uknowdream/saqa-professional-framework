"""Strict certification gates: unknown or incomplete evidence never becomes PASS."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .evidence import EvidenceRecord

@dataclass(frozen=True)
class CertificationResult:
    status: str
    total: int
    counts: dict[str, int]
    reason: str


def certify(records: list[EvidenceRecord], required_total: int | None = None) -> CertificationResult:
    counts = Counter(record.status for record in records)
    total = len(records)
    if required_total is not None and total != required_total:
        return CertificationResult("FAIL", total, dict(counts), "evidence count does not match required test count")
    if not records:
        return CertificationResult("UNVERIFIED", 0, {}, "no evidence records")
    if counts.get("FAIL", 0):
        return CertificationResult("FAIL", total, dict(counts), "one or more executed tests failed")
    if counts.get("BLOCKED", 0) or counts.get("UNVERIFIED", 0):
        return CertificationResult("UNVERIFIED", total, dict(counts), "incomplete evidence cannot be certified")
    if counts.get("NOT_APPLICABLE", 0) and sum(counts.values()) != counts["PASS"] + counts["NOT_APPLICABLE"]:
        return CertificationResult("UNVERIFIED", total, dict(counts), "invalid evidence state")
    return CertificationResult("PASS", total, dict(counts), "all applicable evidence passed")

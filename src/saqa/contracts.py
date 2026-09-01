"""Framework-wide contracts for deterministic QA execution and certification."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ResultStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    UNVERIFIED = "UNVERIFIED"
    NA = "N/A"


@dataclass(frozen=True)
class Evidence:
    test_id: str
    capability: str
    status: ResultStatus
    started_at: str
    finished_at: str
    duration_ms: float
    details: dict[str, Any] = field(default_factory=dict)
    artifact_paths: tuple[str, ...] = ()

    @classmethod
    def now(
        cls,
        test_id: str,
        capability: str,
        status: ResultStatus,
        *,
        duration_ms: float = 0.0,
        details: dict[str, Any] | None = None,
        artifact_paths: tuple[str, ...] = (),
    ) -> "Evidence":
        timestamp = datetime.now(timezone.utc).isoformat()
        return cls(test_id, capability, status, timestamp, timestamp, duration_ms, details or {}, artifact_paths)


def validate_evidence(item: Evidence) -> None:
    if not item.test_id.strip():
        raise ValueError("test_id must not be empty")
    if not item.capability.strip():
        raise ValueError("capability must not be empty")
    if item.duration_ms < 0:
        raise ValueError("duration_ms must not be negative")
    if not item.started_at or not item.finished_at:
        raise ValueError("execution timestamps are required")


def is_certification_safe(status: ResultStatus) -> bool:
    """Only PASS and explicit N/A are non-blocking certification states."""
    return status in {ResultStatus.PASS, ResultStatus.NA}

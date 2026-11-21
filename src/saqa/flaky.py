"""Deterministic flakiness analysis for ordered execution histories."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

_ALLOWED = {"PASS", "FAIL", "SKIP", "BLOCKED", "UNVERIFIED", "N/A", "NOT_APPLICABLE"}


@dataclass(frozen=True)
class FlakyAnalysis:
    """Auditable classification of one test execution history."""

    status: str
    executions: int
    pass_count: int
    fail_count: int
    other_count: int
    transition_count: int

    @property
    def is_flaky(self) -> bool:
        return self.status == "FLAKY"

    @property
    def pass_rate(self) -> float:
        if self.executions == 0:
            return 0.0
        return round(self.pass_count / self.executions, 4)

    @property
    def fail_rate(self) -> float:
        if self.executions == 0:
            return 0.0
        return round(self.fail_count / self.executions, 4)

    @property
    def flakiness_score(self) -> float:
        """Normalized instability score in [0.0, 1.0] based on state transitions."""
        if not self.is_flaky or self.executions < 2:
            return 0.0
        return round(self.transition_count / (self.executions - 1), 4)

    @property
    def quarantine_recommended(self) -> bool:
        """Recommend quarantine when repeated intermittent transitions are observed."""
        return self.is_flaky and self.executions >= 3 and self.flakiness_score >= 0.25


def analyze_history(statuses: Sequence[str] | Iterable[str]) -> FlakyAnalysis:
    """Classify an execution history without inventing retries or outcomes."""
    normalized = [
        "NOT_APPLICABLE"
        if str(getattr(status, "value", status)).upper() == "N/A"
        else str(getattr(status, "value", status)).upper()
        for status in statuses
    ]
    unknown = sorted(set(normalized) - _ALLOWED)
    if unknown:
        raise ValueError(f"unsupported execution status(es): {', '.join(unknown)}")

    passes = normalized.count("PASS")
    fails = normalized.count("FAIL")
    other = len(normalized) - passes - fails
    transitions = sum(a != b for a, b in zip(normalized, normalized[1:]))

    if len(normalized) < 2:
        classification = "INSUFFICIENT_DATA"
    elif passes and fails:
        classification = "FLAKY"
    elif passes == len(normalized):
        classification = "STABLE_PASS"
    elif fails == len(normalized):
        classification = "STABLE_FAIL"
    else:
        classification = "NON_TERMINAL"

    return FlakyAnalysis(classification, len(normalized), passes, fails, other, transitions)


def analyze_suite_flakiness(histories: Mapping[str, Sequence[str]]) -> dict[str, Any]:
    """Analyze and rank stability across an entire test suite."""
    per_test: dict[str, dict[str, Any]] = {}
    counts: dict[str, int] = {
        "FLAKY": 0,
        "STABLE_PASS": 0,
        "STABLE_FAIL": 0,
        "NON_TERMINAL": 0,
        "INSUFFICIENT_DATA": 0,
    }
    flaky_ranking: list[dict[str, Any]] = []
    quarantine_candidates: list[str] = []

    for test_id in sorted(histories):
        analysis = analyze_history(histories[test_id])
        counts[analysis.status] = counts.get(analysis.status, 0) + 1
        entry = {
            "test_id": test_id,
            "status": analysis.status,
            "executions": analysis.executions,
            "pass_count": analysis.pass_count,
            "fail_count": analysis.fail_count,
            "other_count": analysis.other_count,
            "transition_count": analysis.transition_count,
            "pass_rate": analysis.pass_rate,
            "fail_rate": analysis.fail_rate,
            "flakiness_score": analysis.flakiness_score,
            "quarantine_recommended": analysis.quarantine_recommended,
        }
        per_test[test_id] = entry
        if analysis.is_flaky:
            flaky_ranking.append(entry)
        if analysis.quarantine_recommended:
            quarantine_candidates.append(test_id)

    flaky_ranking.sort(
        key=lambda item: (-item["flakiness_score"], -item["transition_count"], item["test_id"])
    )
    return {
        "total_tests": len(per_test),
        "counts": counts,
        "flaky_tests": flaky_ranking,
        "quarantine_candidates": quarantine_candidates,
        "tests": per_test,
    }

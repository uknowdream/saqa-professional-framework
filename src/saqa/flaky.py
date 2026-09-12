"""Deterministic flakiness analysis for ordered execution histories.

The analyzer is intentionally pure: it never reruns tests and never labels a
single failure as flaky. A test is classified as FLAKY only when the observed
history contains both PASS and FAIL outcomes and therefore demonstrates
instability across executions.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence


_ALLOWED = {"PASS", "FAIL", "SKIP", "BLOCKED", "UNVERIFIED"}


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


def analyze_history(statuses: Sequence[str] | Iterable[str]) -> FlakyAnalysis:
    """Classify an execution history without inventing retries or outcomes.

    Rules:
    - fewer than two observations: INSUFFICIENT_DATA;
    - PASS + FAIL in the same history: FLAKY;
    - only PASS: STABLE_PASS;
    - only FAIL: STABLE_FAIL;
    - otherwise: NON_TERMINAL.

    Unknown statuses are rejected so CI evidence cannot silently corrupt the
    classification model.
    """
    normalized = [str(status).upper() for status in statuses]
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

    return FlakyAnalysis(
        status=classification,
        executions=len(normalized),
        pass_count=passes,
        fail_count=fails,
        other_count=other,
        transition_count=transitions,
    )

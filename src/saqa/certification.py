"""Deterministic release certification from canonical QA evidence."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .contracts import ResultStatus


@dataclass(frozen=True)
class CertificationResult:
    certified: bool
    mandatory_capabilities: tuple[str, ...]
    observed_capabilities: tuple[str, ...]
    missing_capabilities: tuple[str, ...]
    blocking_test_ids: tuple[str, ...]
    verified_failure_test_ids: tuple[str, ...] = ()

    @property
    def status(self) -> str:
        """Expose verified FAIL separately from unavailable or incomplete evidence."""
        if self.certified:
            return ResultStatus.PASS.value
        if self.verified_failure_test_ids:
            return ResultStatus.FAIL.value
        return ResultStatus.UNVERIFIED.value


def certify(evidence: Iterable[tuple[str, str, ResultStatus]], mandatory_capabilities: Iterable[str]) -> CertificationResult:
    """Evaluate certification without treating missing evidence as PASS."""
    records = tuple(evidence)
    mandatory = tuple(dict.fromkeys(str(item).strip() for item in mandatory_capabilities if str(item).strip()))
    observed = tuple(sorted({capability for _, capability, _ in records}))
    blocking_records = tuple(
        (test_id, status)
        for test_id, capability, status in records
        if capability in mandatory and status not in {ResultStatus.PASS, ResultStatus.NA}
    )
    blocking = tuple(sorted(test_id for test_id, _ in blocking_records))
    verified_failures = tuple(sorted(test_id for test_id, status in blocking_records if status == ResultStatus.FAIL))
    certifiable = {capability for _, capability, status in records if status in {ResultStatus.PASS, ResultStatus.NA}}
    certified = bool(mandatory) and not missing_capabilities(mandatory, observed) and not blocking and set(mandatory).issubset(certifiable)
    return CertificationResult(certified, mandatory, observed, missing_capabilities(mandatory, observed), blocking, verified_failures)


def missing_capabilities(mandatory: tuple[str, ...], observed: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted(set(mandatory) - set(observed)))

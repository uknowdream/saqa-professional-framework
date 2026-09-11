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


def certify(
    evidence: Iterable[tuple[str, str, ResultStatus]],
    mandatory_capabilities: Iterable[str],
) -> CertificationResult:
    """Evaluate certification without treating missing evidence as PASS.

    Evidence tuples are ``(test_id, capability, status)``. A mandatory
    capability is certifiable only when it has explicit PASS/N/A evidence and
    has no FAIL, BLOCKED, or UNVERIFIED record.
    """
    records = tuple(evidence)
    mandatory = tuple(dict.fromkeys(str(item).strip() for item in mandatory_capabilities if str(item).strip()))
    observed = tuple(sorted({capability for _, capability, _ in records}))
    missing = tuple(sorted(set(mandatory) - set(observed)))
    blocking = tuple(
        sorted(
            test_id
            for test_id, capability, status in records
            if capability in mandatory and status not in {ResultStatus.PASS, ResultStatus.NA}
        )
    )
    certifiable = {
        capability
        for _, capability, status in records
        if status in {ResultStatus.PASS, ResultStatus.NA}
    }
    certified = not missing and not blocking and set(mandatory).issubset(certifiable)
    return CertificationResult(certified, mandatory, observed, missing, blocking)

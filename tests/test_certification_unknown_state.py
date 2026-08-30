import pytest

from saqa.certification import certify
from saqa.evidence import EvidenceRecord


def test_unknown_status_is_rejected_at_evidence_boundary():
    with pytest.raises(ValueError, match="invalid status"):
        EvidenceRecord(
            test_id="T-001",
            status="MYSTERY",
            observed_at="2026-08-30T00:00:00+00:00",
            target="unit",
            details={},
        )


def test_certification_never_certifies_empty_evidence():
    result = certify([])
    assert result.status == "UNVERIFIED"

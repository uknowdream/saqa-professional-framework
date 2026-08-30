from saqa.certification import certify
from saqa.evidence import EvidenceRecord


def test_unknown_status_fails_closed():
    record = EvidenceRecord(test_id="T-001", status="MYSTERY", evidence={})
    result = certify([record])
    assert result.status == "FAIL"
    assert "unknown" in result.reason

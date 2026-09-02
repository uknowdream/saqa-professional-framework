from pathlib import Path

from saqa.certification import certify
from saqa.evidence import EvidenceRecord, verify_manifest, write_manifest


def record(status: str, test_id: str = "T-001") -> EvidenceRecord:
    return EvidenceRecord(test_id, status, "2026-08-30T00:00:00+00:00", "local", {})


def test_all_pass_certifies():
    result = certify([record("PASS"), record("PASS", "T-002")], required_total=2)
    assert result.status == "PASS"


def test_fail_never_certifies():
    result = certify([record("PASS"), record("FAIL", "T-002")], required_total=2)
    assert result.status == "FAIL"


def test_blocked_is_not_pass():
    result = certify([record("PASS"), record("BLOCKED", "T-002")], required_total=2)
    assert result.status == "UNVERIFIED"


def test_missing_evidence_fails_closed():
    result = certify([record("PASS")], required_total=2)
    assert result.status == "FAIL"


def test_manifest_detects_tampering(tmp_path: Path):
    path = tmp_path / "manifest.json"
    write_manifest([record("PASS")], path)
    assert verify_manifest(path)
    path.write_text(path.read_text().replace('"PASS"', '"FAIL"'), encoding="utf-8")
    assert not verify_manifest(path)

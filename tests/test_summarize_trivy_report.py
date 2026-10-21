import json
from pathlib import Path

import pytest

from scripts.summarize_trivy_report import SCHEMA, summarize_file, summarize_report


def report():
    return {"ArtifactName": "example:1", "Results": [{
        "Target": "alpine:3.20",
        "Vulnerabilities": [{"VulnerabilityID": "CVE-2026-1234", "Severity": "HIGH", "FixedVersion": "3.20.1"}],
        "Secrets": [{"RuleID": "private-key", "Severity": "CRITICAL"}],
        "Misconfigurations": [{"ID": "AVD-TEST-1", "Severity": "MEDIUM"}],
    }]}


def test_summary_counts_findings_by_severity():
    result = summarize_report(report(), image="example:1", scanner="trivy-0.76.0")
    assert result["schema"] == SCHEMA
    assert result["finding_count"] == 3
    assert result["by_severity"]["HIGH"] == 1
    assert result["by_severity"]["CRITICAL"] == 1
    assert result["by_severity"]["MEDIUM"] == 1
    assert result["enforcement"].startswith("report-only")


@pytest.mark.parametrize("bad", [None, [], "report", {}])
def test_invalid_report_root_or_missing_results_is_rejected(bad):
    with pytest.raises(ValueError, match="Trivy report|Results array"):
        summarize_report(bad, image="example:1", scanner="trivy-0.76.0")


@pytest.mark.parametrize("field", ["Vulnerabilities", "Secrets", "Misconfigurations"])
def test_malformed_finding_collection_is_rejected(field):
    bad = {"ArtifactName": "example:1", "Results": [{"Target": "image", field: {"unexpected": "object"}}]}
    with pytest.raises(ValueError, match="must be an array"):
        summarize_report(bad, image="example:1", scanner="trivy-0.76.0")


def test_non_object_result_and_finding_are_rejected():
    with pytest.raises(ValueError, match=r"Results\[0\] must be an object"):
        summarize_report({"ArtifactName": "example:1", "Results": ["bad"]}, image="example:1", scanner="trivy-0.76.0")
    with pytest.raises(ValueError, match="must be an object"):
        summarize_report({"ArtifactName": "example:1", "Results": [{"Vulnerabilities": [False]}]}, image="example:1", scanner="trivy-0.76.0")


def test_unsupported_severity_is_rejected():
    bad = {"ArtifactName": "example:1", "Results": [{"Vulnerabilities": [{"VulnerabilityID": "CVE-X", "Severity": "SEVERE"}]}]}
    with pytest.raises(ValueError, match="unsupported severity"):
        summarize_report(bad, image="example:1", scanner="trivy-0.76.0")


def test_empty_target_metadata_is_rejected():
    with pytest.raises(ValueError, match="image must be a non-empty string"):
        summarize_report({"ArtifactName": "example:1", "Results": []}, image=" ", scanner="trivy-0.76.0")


def test_report_file_is_normalized_and_written(tmp_path):
    source, output = tmp_path / "trivy.json", tmp_path / "summary.json"
    source.write_text(json.dumps(report()), encoding="utf-8")
    result = summarize_file(source, output, image="example:1", scanner="trivy-0.76.0")
    import hashlib
    assert result["source_report_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert json.loads(output.read_text(encoding="utf-8")) == result


def test_malformed_json_file_fails_closed(tmp_path):
    source = tmp_path / "trivy.json"
    source.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="cannot read Trivy report"):
        summarize_file(source, tmp_path / "summary.json", image="example:1", scanner="trivy-0.76.0")


def test_requested_image_must_match_actual_trivy_artifact_name():
    data = report()
    data["ArtifactName"] = "attacker/production:latest"
    with pytest.raises(ValueError, match="does not match Trivy-scanned ArtifactName"):
        summarize_report(data, image="bkimminich/juice-shop:v20.2.0", scanner="trivy-0.76.0")


def test_missing_scanned_artifact_identity_is_rejected():
    with pytest.raises(ValueError, match="actual scanned ArtifactName"):
        summarize_report({"Results": []}, image="example:1", scanner="trivy-0.76.0")


def test_raw_report_and_summary_output_must_be_distinct(tmp_path):
    source = tmp_path / "report.json"
    source.write_text(json.dumps(report()), encoding="utf-8")
    original = source.read_bytes()
    with pytest.raises(ValueError, match="must be different files"):
        summarize_file(source, source, image="example:1", scanner="trivy-0.76.0")
    assert source.read_bytes() == original

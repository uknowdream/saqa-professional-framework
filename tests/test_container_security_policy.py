import copy
from datetime import date

import pytest

from scripts.evaluate_container_security_policy import evaluate_summary, validate_policy

POLICY = {
    "schema": "saqa.container-security-policy.v1",
    "policy_id": "test-policy",
    "version": 1,
    "blocking_rules": [
        {"type": "secret", "severities": ["UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL"]},
        {"type": "misconfiguration", "severities": ["HIGH", "CRITICAL"]},
        {"type": "vulnerability", "severities": ["CRITICAL"]},
    ],
    "exceptions": [],
}
SUMMARY = {
    "schema": "saqa.container-security-summary.v1",
    "image": "example:1",
    "scanned_artifact_name": "example:1",
    "findings": [
        {"type": "vulnerability", "severity": "CRITICAL", "id": "CVE-TEST-1", "target": "pkg/a"},
        {"type": "vulnerability", "severity": "HIGH", "id": "CVE-TEST-2", "target": "pkg/b"},
        {"type": "secret", "severity": "LOW", "id": "private-key-rule", "target": "config.env"},
    ],
}


def test_unsuppressed_critical_and_secret_findings_fail():
    result = evaluate_summary(SUMMARY, POLICY, today=date(2026, 10, 21))
    assert result["status"] == "FAIL"
    assert result["blocking_count"] == 2
    assert result["suppressed_count"] == 0


def test_exact_active_exception_suppresses_only_matching_finding():
    policy = copy.deepcopy(POLICY)
    policy["exceptions"] = [{
        "finding_type": "vulnerability", "finding_id": "CVE-TEST-1", "severity": "CRITICAL", "target": "pkg/a",
        "reason": "Fix is scheduled in next patch release", "owner": "platform-team",
        "ticket": "SEC-123", "expires_on": "2026-12-01",
    }]
    result = evaluate_summary(SUMMARY, policy, today=date(2026, 10, 21))
    assert result["suppressed_count"] == 1
    assert result["blocking_count"] == 1
    assert result["status"] == "FAIL"


def test_no_blocking_findings_pass():
    summary = {"schema": "saqa.container-security-summary.v1", "image": "example:1", "scanned_artifact_name": "example:1", "findings": [
        {"type": "vulnerability", "severity": "HIGH", "id": "CVE-1", "target": "pkg/a"}
    ]}
    assert evaluate_summary(summary, POLICY, today=date(2026, 10, 21))["status"] == "PASS"


def test_expired_exception_is_rejected():
    policy = copy.deepcopy(POLICY)
    policy["exceptions"] = [{
        "finding_type": "vulnerability", "finding_id": "CVE-TEST-1", "severity": "CRITICAL", "target": "pkg/a",
        "reason": "temporary", "owner": "team", "ticket": "SEC-1", "expires_on": "2026-10-20",
    }]
    with pytest.raises(ValueError, match="expired"):
        validate_policy(policy, today=date(2026, 10, 21))


def test_wildcard_exception_is_rejected():
    policy = copy.deepcopy(POLICY)
    policy["exceptions"] = [{
        "finding_type": "vulnerability", "finding_id": "*", "severity": "CRITICAL", "target": "pkg/a",
        "reason": "temporary", "owner": "team", "ticket": "SEC-1", "expires_on": "2026-12-01",
    }]
    with pytest.raises(ValueError, match="wildcard"):
        validate_policy(policy, today=date(2026, 10, 21))


def test_exception_requires_owner_ticket_reason_and_expiry():
    policy = copy.deepcopy(POLICY)
    policy["exceptions"] = [{"finding_type": "vulnerability", "finding_id": "CVE-1", "target": "pkg/a"}]
    with pytest.raises(ValueError, match="missing required fields"):
        validate_policy(policy, today=date(2026, 10, 21))


def test_invalid_summary_schema_blocks():
    with pytest.raises(ValueError, match="summary schema"):
        evaluate_summary({"schema": "unknown", "findings": []}, POLICY)


def test_blocking_finding_without_stable_id_fails_closed():
    summary = {"schema": "saqa.container-security-summary.v1", "findings": [
        {"type": "secret", "severity": "HIGH", "id": None, "target": "image-layer"}
    ]}
    result = evaluate_summary(summary, POLICY, today=date(2026, 10, 21))
    assert result["status"] == "FAIL"
    assert "lacks stable ID or target" in result["blocking_findings"][0]["reason"]


def test_duplicate_blocking_rule_rejected():
    policy = copy.deepcopy(POLICY)
    policy["blocking_rules"].append({"type": "secret", "severities": ["HIGH"]})
    with pytest.raises(ValueError, match="duplicate blocking rule"):
        validate_policy(policy, today=date(2026, 10, 21))


@pytest.mark.parametrize("bad_type", [[], {}, None])
def test_malformed_blocking_rule_type_is_rejected(bad_type):
    policy = copy.deepcopy(POLICY)
    policy["blocking_rules"][0]["type"] = bad_type
    with pytest.raises(ValueError, match="invalid type"):
        validate_policy(policy, today=date(2026, 10, 21))


@pytest.mark.parametrize("bad_severity", [[], {}, None])
def test_malformed_blocking_severity_is_rejected(bad_severity):
    policy = copy.deepcopy(POLICY)
    policy["blocking_rules"][0]["severities"] = [bad_severity]
    with pytest.raises(ValueError, match="invalid severities"):
        validate_policy(policy, today=date(2026, 10, 21))


@pytest.mark.parametrize("bad_type", [[], {}, None])
def test_malformed_finding_type_is_rejected(bad_type):
    summary = {"schema": "saqa.container-security-summary.v1", "findings": [
        {"type": bad_type, "severity": "HIGH", "id": "finding-1", "target": "image"}
    ]}
    with pytest.raises(ValueError, match="unsupported type or severity"):
        evaluate_summary(summary, POLICY, today=date(2026, 10, 21))


def test_pinned_intentionally_vulnerable_image_is_report_only_not_certified():
    summary = copy.deepcopy(SUMMARY)
    summary["image"] = "bkimminich/juice-shop:v20.2.0"
    summary["scanned_artifact_name"] = "bkimminich/juice-shop:v20.2.0"
    result = evaluate_summary(summary, POLICY, today=date(2026, 10, 21),
                               report_only_expected_vulnerable_target=True)
    assert result["status"] == "REPORT_ONLY"
    assert result["release_gate_eligible"] is False
    assert result["blocking_count"] == 2
    assert "intentionally vulnerable" in result["note"]


def test_report_only_mode_rejects_any_other_image():
    summary = copy.deepcopy(SUMMARY)
    summary["image"] = "example.com/production:latest"
    summary["scanned_artifact_name"] = "example.com/production:latest"
    with pytest.raises(ValueError, match="restricted to the exact pinned"):
        evaluate_summary(summary, POLICY, today=date(2026, 10, 21),
                         report_only_expected_vulnerable_target=True)


def test_exception_expiring_today_is_rejected():
    policy = copy.deepcopy(POLICY)
    policy["exceptions"] = [{
        "finding_type": "vulnerability", "finding_id": "CVE-TEST-1", "severity": "CRITICAL", "target": "pkg/a",
        "reason": "temporary", "owner": "team", "ticket": "SEC-1", "expires_on": "2026-10-21",
    }]
    with pytest.raises(ValueError, match="expires today"):
        validate_policy(policy, today=date(2026, 10, 21))


def test_exception_does_not_suppress_same_finding_at_different_severity():
    policy = copy.deepcopy(POLICY)
    policy["exceptions"] = [{
        "finding_type": "secret", "finding_id": "private-key-rule", "severity": "LOW",
        "target": "config.env", "reason": "reviewed low-severity occurrence",
        "owner": "security-team", "ticket": "SEC-222", "expires_on": "2026-12-01",
    }]
    summary = {"schema": "saqa.container-security-summary.v1", "findings": [
        {"type": "secret", "severity": "CRITICAL", "id": "private-key-rule", "target": "config.env"}
    ]}
    result = evaluate_summary(summary, policy, today=date(2026, 10, 21))
    assert result["suppressed_count"] == 0
    assert result["blocking_count"] == 1
    assert result["status"] == "FAIL"


def test_exception_severity_must_be_supported():
    policy = copy.deepcopy(POLICY)
    policy["exceptions"] = [{
        "finding_type": "vulnerability", "finding_id": "CVE-TEST-1", "severity": "SEVERE",
        "target": "pkg/a", "reason": "temporary", "owner": "team",
        "ticket": "SEC-1", "expires_on": "2026-12-01",
    }]
    with pytest.raises(ValueError, match="severity is invalid"):
        validate_policy(policy, today=date(2026, 10, 21))


@pytest.mark.parametrize("expires_on", ["not-a-date", "2026-13-01", "2026-02-30"])
def test_malformed_exception_expiry_is_rejected(expires_on):
    policy = copy.deepcopy(POLICY)
    policy["exceptions"] = [{
        "finding_type": "vulnerability", "finding_id": "CVE-TEST-1", "severity": "CRITICAL",
        "target": "pkg/a", "reason": "temporary", "owner": "team", "ticket": "SEC-1",
        "expires_on": expires_on,
    }]
    with pytest.raises(ValueError, match="ISO-8601 date"):
        validate_policy(policy, today=date(2026, 10, 21))


def test_duplicate_exception_key_is_rejected():
    policy = copy.deepcopy(POLICY)
    exception = {
        "finding_type": "vulnerability", "finding_id": "CVE-TEST-1", "severity": "CRITICAL",
        "target": "pkg/a", "reason": "temporary", "owner": "team", "ticket": "SEC-1",
        "expires_on": "2026-12-01",
    }
    policy["exceptions"] = [exception, dict(exception)]
    with pytest.raises(ValueError, match="duplicate exception"):
        validate_policy(policy, today=date(2026, 10, 21))


def test_wildcard_exception_target_is_rejected():
    policy = copy.deepcopy(POLICY)
    policy["exceptions"] = [{
        "finding_type": "secret", "finding_id": "private-key-rule", "severity": "CRITICAL",
        "target": "*", "reason": "temporary", "owner": "team", "ticket": "SEC-1",
        "expires_on": "2026-12-01",
    }]
    with pytest.raises(ValueError, match="wildcard"):
        validate_policy(policy, today=date(2026, 10, 21))


@pytest.mark.parametrize(("field", "value"), [
    ("id", []), ("id", "   "), ("target", 42), ("target", " "),
])
def test_invalid_finding_id_or_target_is_rejected(field, value):
    summary = copy.deepcopy(SUMMARY)
    summary["findings"] = [{"type": "secret", "severity": "HIGH", "id": "secret-1", "target": "source.env"}]
    summary["findings"][0][field] = value
    with pytest.raises(ValueError, match=rf"findings\\[0\\].{field}"):
        evaluate_summary(summary, POLICY, today=date(2026, 10, 21))


def test_normalized_image_identity_must_match_trivy_artifact():
    summary = copy.deepcopy(SUMMARY)
    summary["scanned_artifact_name"] = "example.org/other:tag"
    with pytest.raises(ValueError, match="does not match the actual"):
        evaluate_summary(summary, POLICY, today=date(2026, 10, 21))


def test_invalid_input_writes_blocked_policy_evidence(tmp_path):
    import json
    from scripts.evaluate_container_security_policy import main

    summary_path, policy_path, output = tmp_path / "summary.json", tmp_path / "policy.json", tmp_path / "out" / "policy-result.json"
    summary_path.write_text(json.dumps({"schema": "unknown"}), encoding="utf-8")
    policy_path.write_text(json.dumps(POLICY), encoding="utf-8")
    assert main(["--summary", str(summary_path), "--policy", str(policy_path), "--output", str(output)]) == 2
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "BLOCKED"
    assert payload["release_gate_eligible"] is False


def test_suppressed_finding_preserves_exception_reason():
    policy = copy.deepcopy(POLICY)
    exception = {
        "finding_type": "vulnerability", "finding_id": "CVE-TEST-1", "severity": "CRITICAL",
        "target": "pkg/a", "reason": "fix queued in SEC-123", "owner": "team", "ticket": "SEC-123",
        "expires_on": "2026-12-01",
    }
    policy["exceptions"] = [exception]
    result = evaluate_summary(SUMMARY, policy, today=date(2026, 10, 21))
    assert result["suppressed_findings"][0]["exception"]["reason"] == exception["reason"]

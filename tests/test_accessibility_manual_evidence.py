import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.validate_accessibility_manual_evidence import (
    KEYBOARD_IDS,
    SCHEMA,
    SCREEN_READER_IDS,
    main,
    validate_manual_accessibility_evidence,
)

SHA = "a" * 40


def payload(status_overrides=None):
    status_overrides = status_overrides or {}
    records = []
    for test_id in sorted(KEYBOARD_IDS | SCREEN_READER_IDS):
        status = status_overrides.get(test_id, "PASS")
        environment = {
            "platform": "Windows",
            "os_version": "11 24H2",
            "browser": "Firefox",
            "browser_version": "145.0",
            "viewport": "1440x900",
            "assistive_technology": "NVDA" if test_id in SCREEN_READER_IDS else "None (keyboard-only)",
            "assistive_technology_version": "2026.1" if test_id in SCREEN_READER_IDS else "N/A (keyboard-only)",
        }
        row = {
            "test_id": test_id,
            "status": status,
            "tested_at": "2026-10-21T10:00:00Z",
            "environment": environment,
        }
        if status in {"PASS", "FAIL"}:
            row.update({
                "steps_summary": "Executed the documented manual procedure.",
                "expected": "Keyboard and assistive technology behavior matches the test plan.",
                "actual": "Observed behavior recorded by the tester.",
                "evidence_refs": [f"artifacts/accessibility/{test_id}.png"],
            })
        elif status == "N/A":
            row.update({"na_reason": "Criterion does not apply to this target journey.", "reviewer": "Accessibility Reviewer"})
        else:
            row["reason"] = "No execution evidence available for this criterion."
        records.append(row)
    return {
        "schema": SCHEMA,
        "target": {"url": "https://test.example.invalid", "build": "build-123", "commit_sha": SHA},
        "tester": "Manual Accessibility Tester",
        "run_id": "manual-run-001",
        "recorded_at": "2026-10-21T10:30:00Z",
        "records": records,
    }


def test_complete_manual_matrix_passes_only_when_every_case_has_execution_evidence():
    result = validate_manual_accessibility_evidence(payload())
    assert result["status"] == "PASS"
    assert result["test_count"] == 14
    assert result["status_counts"]["PASS"] == 14
    assert result["evidence_contract_only"] is True


def test_missing_matrix_case_is_rejected():
    value = payload()
    value["records"] = [record for record in value["records"] if record["test_id"] != "SR-06"]
    with pytest.raises(ValueError, match="matrix is incomplete.*SR-06"):
        validate_manual_accessibility_evidence(value)


def test_duplicate_test_id_is_rejected():
    value = payload()
    value["records"].append(dict(value["records"][0]))
    with pytest.raises(ValueError, match="duplicate manual accessibility test ID"):
        validate_manual_accessibility_evidence(value)


def test_unverified_case_cannot_be_inferred_as_pass():
    value = payload({"KBD-04": "UNVERIFIED"})
    result = validate_manual_accessibility_evidence(value)
    assert result["status"] == "UNVERIFIED"
    assert result["status_counts"]["UNVERIFIED"] == 1


def test_failure_takes_precedence_over_unverified():
    value = payload({"KBD-04": "UNVERIFIED", "SR-02": "FAIL"})
    result = validate_manual_accessibility_evidence(value)
    assert result["status"] == "FAIL"


def test_pass_without_evidence_reference_is_rejected():
    value = payload()
    next(record for record in value["records"] if record["test_id"] == "KBD-01")["evidence_refs"] = []
    with pytest.raises(ValueError, match="non-empty array of evidence references"):
        validate_manual_accessibility_evidence(value)


def test_placeholder_evidence_reference_is_rejected():
    value = payload()
    next(record for record in value["records"] if record["test_id"] == "KBD-01")["evidence_refs"] = ["TODO"]
    with pytest.raises(ValueError, match="cannot be a placeholder"):
        validate_manual_accessibility_evidence(value)


def test_screen_reader_case_requires_real_assistive_technology():
    value = payload()
    sr = next(record for record in value["records"] if record["test_id"] == "SR-01")
    sr["environment"]["assistive_technology"] = "N/A"
    with pytest.raises(ValueError, match="requires the actual assistive technology"):
        validate_manual_accessibility_evidence(value)


def test_na_requires_review_and_reason():
    value = payload({"SR-06": "N/A"})
    record = next(row for row in value["records"] if row["test_id"] == "SR-06")
    record.pop("reviewer")
    with pytest.raises(ValueError, match="reviewer"):
        validate_manual_accessibility_evidence(value)


def test_timezone_is_mandatory():
    value = payload()
    value["records"][0]["tested_at"] = "2026-10-21T10:00:00"
    with pytest.raises(ValueError, match="must include a timezone"):
        validate_manual_accessibility_evidence(value)


def test_invalid_commit_sha_is_rejected():
    value = payload()
    value["target"]["commit_sha"] = "not-a-sha"
    with pytest.raises(ValueError, match="commit_sha"):
        validate_manual_accessibility_evidence(value)


def test_future_test_timestamp_is_rejected():
    value = payload()
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    value["records"][0]["tested_at"] = future.isoformat()
    with pytest.raises(ValueError, match="must not be in the future"):
        validate_manual_accessibility_evidence(value)


def test_cli_removes_stale_pass_output_if_new_input_is_invalid(tmp_path):
    source = tmp_path / "bad.json"
    output = tmp_path / "validated.json"
    source.write_text(json.dumps({"schema": "wrong"}), encoding="utf-8")
    output.write_text(json.dumps({"status": "PASS"}), encoding="utf-8")
    assert main(["--input", str(source), "--output", str(output)]) == 2
    assert not output.exists()

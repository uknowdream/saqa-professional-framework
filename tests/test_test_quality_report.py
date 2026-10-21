import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from scripts.test_quality_report import POLICY_SCHEMA, summarize_junit, validate_quarantine_policy


def policy(entries=None):
    return {"schema": POLICY_SCHEMA, "version": 1, "quarantines": entries or []}


def junit(tmp_path, body=None):
    path = tmp_path / "junit.xml"
    path.write_text(body or """<testsuites><testsuite name="unit" tests="3">
      <testcase classname="tests.test_a" name="test_fast" time="0.1"/>
      <testcase classname="tests.test_a" name="test_slow" time="2.0"/>
      <testcase classname="tests.test_b" name="test_skip" time="0.0"><skipped/></testcase>
    </testsuite></testsuites>""", encoding="utf-8")
    return path


def entry(test_id="tests.test_a::test_slow", expiry="2026-12-01"):
    return {"test_id": test_id, "owner": "qa-platform", "reason": "tracked intermittent environment failure",
            "ticket": "QA-123", "expires_on": expiry}


def test_junit_summary_counts_duration_and_slowest(tmp_path):
    result = summarize_junit(junit(tmp_path), policy(), today=date(2026, 10, 21),
                             generated_at=datetime(2026, 10, 21, tzinfo=timezone.utc))
    assert result["status"] == "PASS"
    assert result["test_count"] == 3
    assert result["pass_count"] == 2
    assert result["skipped_count"] == 1
    assert result["total_test_duration_seconds"] == 2.1
    assert result["slowest_tests"][0]["test_id"] == "tests.test_a::test_slow"


def test_expired_quarantine_fails_validation():
    with pytest.raises(ValueError, match="expired or expires today"):
        validate_quarantine_policy(policy([entry(expiry="2026-10-21")]), today=date(2026, 10, 21))


def test_duplicate_quarantine_id_rejected():
    with pytest.raises(ValueError, match="duplicate quarantine"):
        validate_quarantine_policy(policy([entry(), entry()]), today=date(2026, 10, 21))


def test_stale_quarantine_identifier_fails_report(tmp_path):
    result = summarize_junit(junit(tmp_path), policy([entry("tests.missing::test_ghost")]),
                             today=date(2026, 10, 21))
    assert result["status"] == "FAIL"
    assert result["stale_quarantine_ids"] == ["tests.missing::test_ghost"]


def test_quarantined_failure_stays_visible_and_fails(tmp_path):
    xml = """<testsuite name="unit" tests="1"><testcase classname="tests.test_a" name="test_slow" time="0.3"><failure message="broken"/></testcase></testsuite>"""
    result = summarize_junit(junit(tmp_path, xml), policy([entry()]), today=date(2026, 10, 21))
    assert result["status"] == "FAIL"
    assert result["quarantined_failures"] == ["tests.test_a::test_slow"]
    assert result["failure_count"] == 1


def test_invalid_junit_rejected(tmp_path):
    path = tmp_path / "bad.xml"
    path.write_text("<testsuites>", encoding="utf-8")
    with pytest.raises(ValueError, match="cannot parse JUnit"):
        summarize_junit(path, policy(), today=date(2026, 10, 21))


def test_non_finite_test_duration_rejected(tmp_path):
    path = junit(tmp_path, '<testsuite><testcase classname="a" name="b" time="nan"/></testsuite>')
    with pytest.raises(ValueError, match="finite and non-negative"):
        summarize_junit(path, policy(), today=date(2026, 10, 21))


def test_timezone_naive_report_time_rejected(tmp_path):
    with pytest.raises(ValueError, match="timezone-aware"):
        summarize_junit(junit(tmp_path), policy(), generated_at=datetime(2026, 10, 21))


def test_default_quarantine_expiry_uses_utc_calendar_date(monkeypatch):
    import scripts.test_quality_report as report_module

    class FixedUtcDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            assert tz is timezone.utc
            return cls(2026, 10, 21, 0, 15, tzinfo=timezone.utc)

    monkeypatch.setattr(report_module, "datetime", FixedUtcDateTime)
    with pytest.raises(ValueError, match="expired or expires today"):
        report_module.validate_quarantine_policy(policy([entry(expiry="2026-10-21")]))

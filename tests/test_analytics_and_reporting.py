"""Tests for SAQA analytics, diff engine, history trends, and HTML/Markdown reporting."""
from __future__ import annotations

import pytest

from saqa.analytics import (
    analyze_history_file,
    analyze_manifest,
    analyze_records,
    compare_manifests,
    compute_latency_stats,
)
from saqa.evidence import EvidenceRecord, utc_now, write_manifest
from saqa.history import append_history
from saqa.reporting import render_html_report, render_markdown_report


def _rec(test_id: str, status: str, elapsed_ms: float, *, reasons: list[str] | None = None) -> EvidenceRecord:
    details = {"elapsed_ms": elapsed_ms, "checks_passed": ["status"]}
    if reasons:
        details["failure_reasons"] = reasons
    return EvidenceRecord(
        test_id=test_id,
        status=status,
        observed_at=utc_now(),
        target="http://127.0.0.1:3000",
        details=details,
    )


def test_compute_latency_stats_percentiles_and_empty():
    empty = compute_latency_stats([])
    assert empty["count"] == 0 and empty["p95_ms"] == 0.0

    stats = compute_latency_stats([10.0, 20.0, 30.0, 40.0, 100.0])
    assert stats["count"] == 5
    assert stats["min_ms"] == 10.0
    assert stats["p50_ms"] == 30.0
    assert stats["max_ms"] == 100.0
    assert stats["p95_ms"] > stats["p50_ms"]
    assert stats["stdev_ms"] > 0


def test_analyze_manifest_health_score_and_fail_closed(tmp_path):
    manifest = tmp_path / "manifest.json"
    records = [
        _rec("t-pass-1", "PASS", 45.0),
        _rec("t-pass-2", "PASS", 120.0),
        _rec("t-fail-1", "FAIL", 240.0, reasons=["status: expected 200"]),
        _rec("t-blocked-1", "BLOCKED", 10.0),
    ]
    write_manifest(records, manifest)
    stats = analyze_manifest(manifest)
    assert stats["overall_status"] == "FAIL"
    assert stats["pass_rate_pct"] == 50.0
    assert stats["health_score"] < 50.0
    assert stats["health_grade"] == "F"
    assert stats["slowest_tests"][0]["test_id"] == "t-fail-1"
    assert len(stats["failing_tests"]) == 1
    assert stats["blocked_tests"] == ["t-blocked-1"]

    # Tampered manifest must fail closed
    manifest.write_text('{"records": [], "sha256": "0"}', encoding="utf-8")
    with pytest.raises(ValueError, match="integrity verification"):
        analyze_manifest(manifest)


def test_compare_manifests_detects_regressions_fixes_and_latency_drift(tmp_path):
    base_path = tmp_path / "base.json"
    curr_path = tmp_path / "curr.json"
    write_manifest(
        [
            _rec("stable-ok", "PASS", 50.0),
            _rec("will-regress", "PASS", 40.0),
            _rec("will-fix", "FAIL", 60.0),
            _rec("will-slow-down", "PASS", 40.0),
            _rec("removed-test", "PASS", 30.0),
        ],
        base_path,
    )
    write_manifest(
        [
            _rec("stable-ok", "PASS", 52.0),
            _rec("will-regress", "FAIL", 45.0, reasons=["schema mismatch"]),
            _rec("will-fix", "PASS", 55.0),
            _rec("will-slow-down", "PASS", 120.0),
            _rec("added-test", "PASS", 20.0),
        ],
        curr_path,
    )

    diff = compare_manifests(base_path, curr_path)
    assert diff["verdict"] == "REGRESSED"
    assert [x["test_id"] for x in diff["new_failures"]] == ["will-regress"]
    assert [x["test_id"] for x in diff["fixed"]] == ["will-fix"]
    assert diff["added_tests"] == ["added-test"]
    assert diff["removed_tests"] == ["removed-test"]
    assert [x["test_id"] for x in diff["latency_regressions"]] == ["will-slow-down"]


def test_analyze_history_file_and_render_reports_with_xss_escaping(tmp_path):
    history_path = tmp_path / "history.jsonl"
    append_history([_rec("flaky-1", "PASS", 30.0), _rec("ok-1", "PASS", 20.0)], history_path, commit_sha="aaa111")
    append_history([_rec("flaky-1", "FAIL", 55.0), _rec("ok-1", "PASS", 22.0)], history_path, commit_sha="bbb222")
    append_history([_rec("flaky-1", "PASS", 31.0), _rec("ok-1", "PASS", 21.0)], history_path, commit_sha="ccc333")

    hist = analyze_history_file(history_path)
    assert hist["chain_verified"] is True
    assert hist["commit_count"] == 3
    assert hist["flakiness"]["quarantine_candidates"] == ["flaky-1"]

    xss_records = [
        _rec("<script>alert(1)</script>", "FAIL", 80.0, reasons=["<b>bad</b>"]),
        _rec("safe-pass", "PASS", 25.0),
    ]
    stats = analyze_records(xss_records, manifest_sha256="a" * 64)

    md = render_markdown_report(stats, history=hist, title="QA Run")
    assert "# QA Run" in md
    assert "Health Score" in md
    assert "flaky-1" in md

    html_doc = render_html_report(stats, xss_records, history=hist, manifest_sha256="a" * 64, title="<QA Report>")
    assert "<script>alert(1)</script>" not in html_doc
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_doc
    assert "&lt;QA Report&gt;" in html_doc
    assert "data-filter=\"FAIL\"" in html_doc


def test_render_reports_include_baseline_diff_sections(tmp_path):
    base_path = tmp_path / "base.json"
    curr_path = tmp_path / "curr.json"
    base_recs = [_rec("a", "PASS", 40.0), _rec("b", "FAIL", 50.0), _rec("c", "PASS", 30.0)]
    curr_recs = [_rec("a", "FAIL", 45.0, reasons=["boom"]), _rec("b", "PASS", 45.0), _rec("c", "PASS", 100.0)]
    write_manifest(base_recs, base_path)
    write_manifest(curr_recs, curr_path)
    diff = compare_manifests(base_path, curr_path)
    stats = analyze_manifest(curr_path)

    md = render_markdown_report(stats, diff=diff)
    assert "Baseline Comparison (`REGRESSED`)" in md
    assert "Regression `a`" in md
    assert "Latency regression `c`" in md

    html_doc = render_html_report(stats, curr_recs, diff=diff)
    assert "NEW FAIL" in html_doc
    assert "FIXED" in html_doc
    assert "SLOWER" in html_doc

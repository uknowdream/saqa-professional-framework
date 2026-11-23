"""Unit tests for saqa.visual_evidence (PNG scorecard, SVG chart, CSV export, screenshot guards)."""
from __future__ import annotations

import csv
import struct

import pytest

from saqa.analytics import analyze_records
from saqa.evidence import EvidenceRecord, utc_now
from saqa.visual_evidence import (
    capture_web_screenshot,
    export_csv_matrix,
    render_analytics_svg,
    render_scorecard_png,
)


def _sample_records() -> list[EvidenceRecord]:
    return [
        EvidenceRecord(
            test_id="homepage-load",
            status="PASS",
            observed_at=utc_now(),
            target="https://www.dreamex.tech",
            details={
                "case_name": "Homepage loads within SLA",
                "http_method": "GET",
                "status_code": 200,
                "elapsed_ms": 145.2,
                "tags": ["web", "smoke"],
                "checks_passed": ["status", "max_ms"],
            },
        ),
        EvidenceRecord(
            test_id="security-headers",
            status="FAIL",
            observed_at=utc_now(),
            target="https://www.dreamex.tech",
            details={
                "case_name": "Strict headers check",
                "http_method": "GET",
                "status_code": 200,
                "elapsed_ms": 210.5,
                "tags": ["security"],
                "failure_reasons": ["missing x-frame-options"],
            },
        ),
    ]


def test_render_scorecard_png_writes_valid_960x540_png(tmp_path):
    records = _sample_records()
    analytics = analyze_records(records, manifest_sha256="a" * 64)
    out = render_scorecard_png(analytics, records, tmp_path / "scorecard.png", title="SAQA | DreamEx")
    data = out.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", data[16:24])
    assert (width, height) == (960, 540)


def test_render_analytics_svg_and_export_csv_matrix(tmp_path):
    records = _sample_records()
    analytics = analyze_records(records, manifest_sha256="b" * 64)

    svg_path = render_analytics_svg(analytics, records, tmp_path / "chart.svg", title="DreamEx <QA>")
    svg_text = svg_path.read_text(encoding="utf-8")
    assert svg_text.startswith("<svg ")
    assert "DreamEx &lt;QA&gt;" in svg_text
    assert "homepage-load" in svg_text

    csv_path = export_csv_matrix(records, tmp_path / "matrix.csv")
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    assert len(rows) == 3
    assert rows[0][0] == "Test ID"
    assert rows[1][0] == "homepage-load" and rows[1][3] == "PASS"
    assert rows[2][0] == "security-headers" and "missing x-frame-options" in rows[2][9]


def test_capture_web_screenshot_validates_url_safety(tmp_path):
    with pytest.raises(ValueError, match="invalid screenshot target URL"):
        capture_web_screenshot("file:///etc/passwd", tmp_path / "bad.png")
    with pytest.raises(ValueError, match="embedded credentials"):
        capture_web_screenshot("https://user:pass@example.com/", tmp_path / "bad2.png")

"""Comprehensive unit tests for SAQA v2.4.0 features (visual_diff, spa_audit, http_pool, notifications, benchmark, chained/parallel runner, sprint dates)."""
from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path

import pytest

from saqa.analytics import analyze_records
from saqa.api import ApiResponse
from saqa.benchmark import run_multi_target_benchmark
from saqa.cli import main as cli_main
from saqa.evidence import EvidenceRecord, utc_now
from saqa.http_pool import create_pooled_requester
from saqa.jira_sync import _compute_timeline_window
from saqa.notifications import dispatch_notifications, format_alert_message
from saqa.runner import run_suite
from saqa.spa_audit import build_spa_audit_record, inspect_spa_runtime
from saqa.visual_diff import compare_png_images, decode_png_rgb
from saqa.visual_evidence import _png_chunk
from saqa.web_audit import DeepAuditResult


def _make_filtered_png(path: Path, width: int, height: int, color: tuple[int, int, int], filter_type: int = 0) -> Path:
    stride = width * 3
    prev = bytearray(stride)
    raw = bytearray()
    row_pixels = bytearray(bytes(color) * width)
    for _ in range(height):
        raw.append(filter_type)
        filtered = bytearray(stride)
        for i in range(stride):
            left = row_pixels[i - 3] if i >= 3 else 0
            up = prev[i]
            if filter_type == 0:
                filtered[i] = row_pixels[i]
            elif filter_type == 1:
                filtered[i] = (row_pixels[i] - left) & 0xFF
            elif filter_type == 2:
                filtered[i] = (row_pixels[i] - up) & 0xFF
            elif filter_type == 3:
                filtered[i] = (row_pixels[i] - ((left + up) >> 1)) & 0xFF
            elif filter_type == 4:
                # Paeth
                up_left = prev[i - 3] if i >= 3 else 0
                p = left + up - up_left
                pa, pb, pc = abs(p - left), abs(p - up), abs(p - up_left)
                pred = left if (pa <= pb and pa <= pc) else (up if pb <= pc else up_left)
                filtered[i] = (row_pixels[i] - pred) & 0xFF
        raw.extend(filtered)
        prev = bytearray(row_pixels)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png_bytes = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(bytes(raw)))
        + _png_chunk(b"IEND", b"")
    )
    path.write_bytes(png_bytes)
    return path


@pytest.mark.parametrize("filter_type", [0, 1, 2, 3, 4])
def test_decode_png_supports_all_5_scanline_filters(tmp_path, filter_type):
    img = _make_filtered_png(tmp_path / f"f{filter_type}.png", 8, 6, (40, 120, 200), filter_type=filter_type)
    w, h, rgb = decode_png_rgb(img)
    assert (w, h) == (8, 6)
    assert tuple(rgb[:3]) == (40, 120, 200)
    assert tuple(rgb[-3:]) == (40, 120, 200)


def test_visual_diff_detects_identical_changed_and_mismatched_dimensions(tmp_path, capsys):
    base = _make_filtered_png(tmp_path / "base.png", 10, 10, (20, 30, 40))
    same = _make_filtered_png(tmp_path / "same.png", 10, 10, (22, 32, 42))  # within tolerance=10
    diff_img = _make_filtered_png(tmp_path / "changed.png", 10, 10, (200, 30, 40))
    diff_size = _make_filtered_png(tmp_path / "size.png", 12, 10, (20, 30, 40))

    r_ok = compare_png_images(base, same, tmp_path / "out_ok.png", pixel_tolerance=10, max_mismatch_pct=0.5)
    assert r_ok.passed is True
    assert r_ok.mismatch_pixels == 0
    assert (tmp_path / "out_ok.png").is_file()

    r_fail = compare_png_images(base, diff_img, tmp_path / "out_fail.png", pixel_tolerance=10, max_mismatch_pct=0.5)
    assert r_fail.passed is False
    assert r_fail.mismatch_pct == 100.0
    assert r_fail.to_dict()["passed"] is False

    r_dim = compare_png_images(base, diff_size)
    assert r_dim.passed is False and r_dim.dimensions_match is False

    # CLI visual-diff subcommand
    assert cli_main(["visual-diff", str(base), str(same), "--output", str(tmp_path / "cli-diff.png"), "--json"]) == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["passed"] is True
    assert cli_main(["visual-diff", str(base), str(diff_img)]) == 1


def test_spa_audit_record_pass_fail_and_blocked():
    def ok_inspector(url, *, timeout_s=25):
        return {
            "engine": "playwright-chromium",
            "available": True,
            "wall_ms": 180.0,
            "rendered_html": '<html lang="en"><head><title>App</title></head><body><main><h1>Hi</h1><button>Go</button></main></body></html>',
            "dom_node_count": 12,
            "console_errors": [],
            "page_errors": [],
            "failed_requests": [],
            "navigation_timing": {"ttfb_ms": 40, "dom_interactive_ms": 110},
        }

    rec_ok = build_spa_audit_record("https://example.test/", suite_name="s1", inspector=ok_inspector)
    assert rec_ok.status == "PASS"

    def err_inspector(url, *, timeout_s=25):
        return {
            "engine": "playwright-chromium",
            "available": True,
            "wall_ms": 180.0,
            "rendered_html": '<html lang="en"><head><title>App</title></head><body><main><h1>Hi</h1></main></body></html>',
            "dom_node_count": 8,
            "console_errors": ["TypeError: x is undefined"],
            "page_errors": ["Uncaught Error"],
            "failed_requests": ["https://example.test (500)"],
            "navigation_timing": {},
        }

    rec_fail = build_spa_audit_record("https://example.test/", suite_name="s1", inspector=err_inspector)
    assert rec_fail.status == "FAIL"
    assert len(rec_fail.details["failure_reasons"]) == 3

    rec_blocked = build_spa_audit_record(
        "https://example.test/",
        suite_name="s1",
        inspector=lambda u, **kw: {"available": False, "wall_ms": 0.0},
    )
    assert rec_blocked.status == "BLOCKED"

    with pytest.raises(ValueError):
        inspect_spa_runtime("ftp://bad")


def test_runner_chained_extraction_and_parallel_workers(tmp_path):
    def fake_req(url, **kwargs):
        if url.endswith("/catalog"):
            return ApiResponse(
                200,
                {"Content-Type": "application/json", "X-Catalog-Version": "v9"},
                b'{"items":[{"id":77,"slug":"pro-kit"}]}',
                12.0,
            )
        if "/items/77" in url and "ver=v9" in url and "slug=pro-kit" in url:
            return ApiResponse(200, {"Content-Type": "application/json"}, b'{"ok":true,"id":77}', 10.0)
        return ApiResponse(404, {}, b"not found", 5.0, error="HTTP 404")

    chained_suite = {
        "name": "chained-flow",
        "base_url": "http://127.0.0.1:3000",
        "cases": [
            {
                "id": "step-1-list",
                "path": "/catalog",
                "extract": {
                    "item_id": "json:items[0].id",
                    "cat_ver": "header:x-catalog-version",
                    "item_slug": r'regex:"slug":"([^"]+)"',
                },
                "expect": {"status": 200},
            },
            {
                "id": "step-2-detail",
                "path": "/items/{{item_id}}",
                "query": {"ver": "{{cat_ver}}", "slug": "{{item_slug}}"},
                "expect": {"status": 200, "json_paths": [{"path": "id", "equals": 77}]},
            },
        ],
    }
    res_chain = run_suite(chained_suite, requester=fake_req)
    assert res_chain.passed is True
    assert res_chain.records[0].details["extracted_keys"] == ["cat_ver", "item_id", "item_slug"]

    # Parallel workers mode on independent cases
    par_suite = {
        "name": "parallel-flow",
        "base_url": "http://127.0.0.1:3000",
        "concurrency": 4,
        "cases": [
            {"id": f"p-{i}", "path": "/catalog", "expect": {"status": 200}}
            for i in range(6)
        ],
    }
    res_par = run_suite(par_suite, workers=4, requester=fake_req)
    assert res_par.passed is True
    assert [r.test_id for r in res_par.records] == [f"p-{i}" for i in range(6)]


def test_notifications_slack_discord_telegram_and_generic(monkeypatch):
    sent: list[tuple[str, dict]] = []

    def fake_sender(url, payload, *, timeout=10.0):
        sent.append((url, dict(payload)))
        return {"ok": True, "status_code": 200}

    monkeypatch.setenv("SAQA_SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/T1/B1/X1")
    monkeypatch.setenv("SAQA_DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/123/abc")
    monkeypatch.setenv("SAQA_TELEGRAM_BOT_TOKEN", "123:TOKEN")
    monkeypatch.setenv("SAQA_TELEGRAM_CHAT_ID", "-100999")

    rec = EvidenceRecord("c1", "FAIL", utc_now(), "https://example.test", {"elapsed_ms": 55.0, "failure_reasons": ["boom"]})
    analytics = analyze_records([rec])
    msg = format_alert_message(analytics, suite_name="demo", target="https://example.test", jira_url="https://jira.example")
    assert "FAIL" in msg and "c1" in msg

    deliveries = dispatch_notifications(
        analytics,
        suite_name="demo",
        webhook_urls=["https://webhook.example/hook"],
        sender=fake_sender,
    )
    assert len(deliveries) == 4
    assert {d["channel"] for d in deliveries} == {"slack", "discord", "telegram", "webhook"}

    # only_on_failure skips PASS
    pass_analytics = analyze_records([EvidenceRecord("c2", "PASS", utc_now(), "https://example.test", {"elapsed_ms": 10.0})])
    assert dispatch_notifications(pass_analytics, only_on_failure=True, sender=fake_sender) == []


def test_benchmark_and_custom_sprint_timeline_and_http_pool(tmp_path):
    def fake_auditor(url, *, output_dir=None, include_spa_audit=False):
        score = 100.0 if "fast" in url else 85.0
        ms = 120.0 if "fast" in url else 350.0
        recs = (
            EvidenceRecord("pillar-1.tls-certificate-audit", "PASS", utc_now(), url, {"protocol": "TLSv1.3", "days_remaining": 75, "elapsed_ms": ms}),
            EvidenceRecord("pillar-2.security-headers-and-cookies", "PASS", utc_now(), url, {"security_header_score_pct": score, "elapsed_ms": ms}),
            EvidenceRecord("pillar-5.broken-links-and-assets", "PASS", utc_now(), url, {"broken_links": [], "elapsed_ms": ms}),
        )
        analytics = analyze_records(recs)
        analytics["health_score"] = score
        return DeepAuditResult(url, recs, analytics, (), None, "a" * 64, None)

    out_dir = tmp_path / "bench"
    bench = run_multi_target_benchmark(["https://slow.test", "https://fast.test"], output_dir=out_dir, auditor=fake_auditor)
    assert bench["leader"] == "https://fast.test"
    assert (out_dir / "benchmark.html").is_file()
    assert (out_dir / "benchmark.md").is_file()
    assert (out_dir / "benchmark.csv").is_file()

    # Custom sprint dates window
    from datetime import datetime, timezone
    epics, domains = _compute_timeline_window(
        today=datetime(2026, 11, 24, tzinfo=timezone.utc),
        sprint_start="2026-12-01",
        sprint_end="2026-12-21",
    )
    assert epics["PHASE-1"][0] == "2026-12-01"
    assert epics["PHASE-3"][1] == "2026-12-21"
    assert domains["QA-1"][0] == "2026-12-01"
    assert domains["QA-9"][1] == "2026-12-21"
    with pytest.raises(ValueError, match="sprint_start"):
        _compute_timeline_window(today=datetime(2026, 11, 24, tzinfo=timezone.utc), sprint_start="2026-12-25", sprint_end="2026-12-01")

    # Pooled requester context manager smoke
    with create_pooled_requester() as req:
        assert callable(req)


def test_inspect_spa_runtime_validation_and_chromium_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    from types import SimpleNamespace

    from saqa import spa_audit

    with pytest.raises(ValueError, match="invalid SPA audit URL"):
        spa_audit.inspect_spa_runtime("ftp://example.com")
    with pytest.raises(ValueError, match="credentials"):
        spa_audit.inspect_spa_runtime("https://user:pass@example.com/")

    # Force Playwright import failure so fallback path executes
    monkeypatch.setitem(sys.modules, "playwright", None)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)

    monkeypatch.setattr(spa_audit, "_find_chromium_binary", lambda: None)
    no_bin = spa_audit.inspect_spa_runtime("https://example.com")
    assert no_bin["available"] is False
    assert no_bin["engine"] == "none"

    monkeypatch.setattr(spa_audit, "_find_chromium_binary", lambda: "/usr/bin/chromium")
    monkeypatch.setattr(
        spa_audit.subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(
            returncode=0,
            stdout='<!doctype html><html lang="en"><body><h1>SPA OK</h1></body></html>',
            stderr="",
        ),
    )
    ok = spa_audit.inspect_spa_runtime("https://example.com")
    assert ok["available"] is True
    assert ok["engine"] == "chromium-dump-dom"
    assert ok["dom_node_count"] >= 4


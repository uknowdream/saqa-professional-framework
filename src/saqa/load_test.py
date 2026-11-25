"""Built-in Read-Only Concurrent HTTP Load & SLA Stress Tester (Pure Python, Zero External k6 Dependency).

Executes bounded, strictly read-only (GET/HEAD) concurrent load profiles against authorized
loopback or client targets, computing Throughput (RPS), Error Rate, and P50/P90/P95/P99 SLAs.
"""
from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from . import __version__
from .analytics import analyze_records, compute_latency_stats
from .api import ApiResponse
from .evidence import EvidenceRecord, utc_now, write_manifest
from .http_pool import create_pooled_requester
from .i18n import normalize_lang
from .pdf_report import render_pdf_report
from .reporting import render_html_report, render_junit_xml, render_markdown_report
from .url_safety import redact_url
from .visual_evidence import export_csv_matrix, render_analytics_svg, render_scorecard_png

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
MAX_SAFE_CONCURRENCY = 50
MAX_SAFE_REQUESTS = 1000


def run_load_test(
    target_url: str,
    *,
    total_requests: int = 30,
    concurrency: int = 6,
    max_p95_ms: float = 2500.0,
    max_error_rate_pct: float = 1.0,
    timeout: float = 10.0,
    allow_remote: bool = False,
    headers: Mapping[str, str] | None = None,
    output_dir: Path | None = None,
    lang: str = "en",
    requester: Callable[..., ApiResponse] | None = None,
) -> dict[str, Any]:
    """Run a bounded read-only GET load & SLA profile and emit SAQA evidence & reports."""
    parsed = urlparse(target_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"Invalid load-test target URL: {target_url!r}")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Load-test URL must not contain embedded credentials")
    if not allow_remote and parsed.hostname.lower() not in _LOOPBACK_HOSTS:
        raise ValueError(
            f"Remote load test against {parsed.hostname!r} requires explicit allow_remote=True (--allow-remote)"
        )
    if concurrency < 1 or concurrency > MAX_SAFE_CONCURRENCY:
        raise ValueError(f"concurrency must be between 1 and {MAX_SAFE_CONCURRENCY}")
    if total_requests < 1 or total_requests > MAX_SAFE_REQUESTS:
        raise ValueError(f"total_requests must be between 1 and {MAX_SAFE_REQUESTS}")

    code = normalize_lang(lang)
    req_headers: dict[str, str] = {
        "User-Agent": f"SAQA-LoadTester/{__version__}",
        "Accept": "*/*",
        "Accept-Encoding": "identity",
    }
    if headers:
        req_headers.update(headers)

    latencies: list[float] = []
    status_hist: dict[str, int] = {}
    errors = 0

    pool_ctx = create_pooled_requester(max_connections=concurrency + 4) if requester is None else nullcontext(requester)
    with pool_ctx as active_req:
        def _single(_i: int) -> ApiResponse:
            return active_req(
                target_url,
                method="GET",
                headers=req_headers,
                timeout=timeout,
                follow_redirects=True,
                use_environment_proxies=False,
            )

        t_start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            responses = list(executor.map(_single, range(total_requests)))
        wall_s = max(0.001, time.perf_counter() - t_start)

    for resp in responses:
        latencies.append(round(resp.elapsed_ms, 3))
        key = str(resp.status_code)
        status_hist[key] = status_hist.get(key, 0) + 1
        if resp.status_code == 0 or resp.status_code >= 400 or resp.error:
            errors += 1

    latency_stats = compute_latency_stats(latencies)
    rps = round(total_requests / wall_s, 2)
    error_rate_pct = round((errors / total_requests) * 100.0, 2)

    checks = [
        f"requests:{total_requests}",
        f"concurrency:{concurrency}",
        f"rps:{rps}",
        f"error_rate_pct:{error_rate_pct}",
        f"p95_ms:{latency_stats['p95_ms']}",
    ]
    failures: list[str] = []
    if error_rate_pct > max_error_rate_pct:
        failures.append(f"Load error rate {error_rate_pct}% exceeded SLA budget ({max_error_rate_pct}%)")
    if latency_stats["p95_ms"] > max_p95_ms:
        failures.append(f"Load P95 latency {latency_stats['p95_ms']}ms exceeded SLA budget ({max_p95_ms}ms)")

    suite_name = f"load-test-{parsed.hostname}"
    record = EvidenceRecord(
        test_id="load-test.concurrent-sla-profile",
        status="FAIL" if failures else "PASS",
        observed_at=utc_now(),
        target=redact_url(target_url),
        details={
            "suite": suite_name,
            "case_name": f"Concurrent HTTP Load & SLA Stress Gate ({total_requests} req @ c={concurrency})",
            "tags": ["performance", "web", "api"],
            "http_method": "GET",
            "status_code": 200 if errors == 0 else 500,
            "elapsed_ms": latency_stats["p95_ms"],
            "throughput_rps": rps,
            "wall_duration_s": round(wall_s, 3),
            "total_requests": total_requests,
            "concurrency": concurrency,
            "error_count": errors,
            "error_rate_pct": error_rate_pct,
            "status_codes": status_hist,
            "latency": latency_stats,
            "checks_passed": checks,
            "failure_reasons": failures,
        },
    )

    records = [record]
    manifest_path: Path | None = None
    manifest_sha: str | None = None
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = output_dir / "evidence-manifest.json"
        manifest_sha = write_manifest(records, manifest_path)

    analytics = analyze_records(records, manifest_sha256=manifest_sha)

    if output_dir is not None:
        title = f"{'Uji Beban & Performa SAQA' if code == 'id' else 'SAQA Load & SLA Report'} — {parsed.hostname}"
        (output_dir / "suite-summary.json").write_text(
            json.dumps({"suite_name": suite_name, "rps": rps, "error_rate_pct": error_rate_pct, "analytics": analytics}, indent=2),
            encoding="utf-8",
        )
        (output_dir / "report.html").write_text(render_html_report(analytics, records, manifest_sha256=manifest_sha, title=title, lang=code), encoding="utf-8")
        (output_dir / "report.md").write_text(render_markdown_report(analytics, title=title, lang=code), encoding="utf-8")
        render_pdf_report(analytics, records, output_dir / "qa-executive-report.pdf", manifest_sha256=manifest_sha, title=title, lang=code)
        (output_dir / "junit.xml").write_text(render_junit_xml(analytics, records, suite_name=suite_name), encoding="utf-8")
        render_scorecard_png(analytics, records, output_dir / "qa-scorecard.png", title=f"SAQA LOAD | {parsed.hostname}", lang=code)
        render_analytics_svg(analytics, records, output_dir / "qa-analytics-chart.svg", title=title, lang=code)
        export_csv_matrix(records, output_dir / "qa-test-matrix.csv", lang=code)

    return {
        "target_url": redact_url(target_url),
        "suite_name": suite_name,
        "passed": len(failures) == 0,
        "throughput_rps": rps,
        "wall_duration_s": round(wall_s, 3),
        "total_requests": total_requests,
        "concurrency": concurrency,
        "error_count": errors,
        "error_rate_pct": error_rate_pct,
        "status_codes": status_hist,
        "latency": latency_stats,
        "analytics": analytics,
        "manifest_path": str(manifest_path) if manifest_path else None,
        "manifest_sha256": manifest_sha,
    }

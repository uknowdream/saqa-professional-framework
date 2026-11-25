"""Live SPA / Headless Browser DOM & Runtime Auditor (Pillar 8).

Inspects JavaScript-hydrated DOM, console errors, uncaught page exceptions,
failed XHR/fetch network requests, and Navigation Timing metrics via Playwright
or headless Chrome/Chromium/Edge `--dump-dom` fallback.
"""
from __future__ import annotations

import subprocess
import time
from typing import Any
from urllib.parse import urlparse

from .evidence import EvidenceRecord, utc_now
from .url_safety import redact_url
from .visual_evidence import _find_chromium_binary
from .web_audit import _DomAuditParser, _audit_dom_accessibility


def inspect_spa_runtime(
    url: str,
    *,
    timeout_s: int = 25,
) -> dict[str, Any]:
    """Execute a live headless browser render to audit post-JS DOM, console errors, and timing."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"invalid SPA audit URL: {url!r}")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("SPA audit URL must not contain embedded credentials")

    # 1. Prefer full Playwright telemetry (console errors, pageerrors, failed requests, nav timing)
    try:
        from playwright.sync_api import sync_playwright

        console_errors: list[str] = []
        page_errors: list[str] = []
        failed_requests: list[str] = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                page.on(
                    "console",
                    lambda msg: console_errors.append(msg.text[:200]) if msg.type == "error" else None,
                )
                page.on("pageerror", lambda err: page_errors.append(str(err)[:200]))
                page.on(
                    "response",
                    lambda resp: failed_requests.append(f"{redact_url(resp.url)} ({resp.status})")
                    if resp.status >= 400
                    else None,
                )
                t0 = time.perf_counter()
                page.goto(url, wait_until="networkidle", timeout=timeout_s * 1000)
                wall_ms = round((time.perf_counter() - t0) * 1000, 2)
                rendered_html = page.content()
                timing = page.evaluate(
                    """() => {
                        const nav = performance.getEntriesByType('navigation')[0];
                        if (!nav) return {};
                        return {
                            ttfb_ms: Math.round(nav.responseStart - nav.requestStart),
                            dom_interactive_ms: Math.round(nav.domInteractive),
                            load_event_ms: Math.round(nav.loadEventEnd)
                        };
                    }"""
                )
                dom_node_count = int(page.evaluate("() => document.querySelectorAll('*').length"))
                return {
                    "engine": "playwright-chromium",
                    "available": True,
                    "wall_ms": wall_ms,
                    "rendered_html": rendered_html,
                    "dom_node_count": dom_node_count,
                    "console_errors": console_errors[:10],
                    "page_errors": page_errors[:10],
                    "failed_requests": failed_requests[:10],
                    "navigation_timing": timing if isinstance(timing, dict) else {},
                }
            finally:
                browser.close()
    except Exception:
        pass

    # 2. Fallback to system headless Chrome / Chromium / Edge `--dump-dom`
    binary = _find_chromium_binary()
    if not binary:
        return {
            "engine": "none",
            "available": False,
            "wall_ms": 0.0,
            "rendered_html": "",
            "dom_node_count": 0,
            "console_errors": [],
            "page_errors": [],
            "failed_requests": [],
            "navigation_timing": {},
        }

    t0 = time.perf_counter()
    cmd = [
        binary,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--virtual-time-budget=5000",
        "--dump-dom",
        url,
    ]
    completed = subprocess.run(cmd, check=False, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout_s)
    wall_ms = round((time.perf_counter() - t0) * 1000, 2)
    rendered_html = completed.stdout or ""
    if completed.returncode != 0 or "<html" not in rendered_html.lower():
        return {
            "engine": "chromium-dump-dom",
            "available": False,
            "wall_ms": wall_ms,
            "rendered_html": "",
            "dom_node_count": 0,
            "console_errors": [],
            "page_errors": [completed.stderr.strip()[:200]] if completed.stderr else [],
            "failed_requests": [],
            "navigation_timing": {},
        }

    return {
        "engine": "chromium-dump-dom",
        "available": True,
        "wall_ms": wall_ms,
        "rendered_html": rendered_html,
        "dom_node_count": rendered_html.count("<"),
        "console_errors": [],
        "page_errors": [],
        "failed_requests": [],
        "navigation_timing": {},
    }


def build_spa_audit_record(
    target_url: str,
    *,
    suite_name: str,
    timeout_s: int = 25,
    inspector=inspect_spa_runtime,
) -> EvidenceRecord:
    """Run Pillar 8 SPA post-JS render audit and return a canonical EvidenceRecord."""
    redacted = redact_url(target_url)
    info = inspector(target_url, timeout_s=timeout_s)
    if not info.get("available"):
        return EvidenceRecord(
            test_id="pillar-8.spa-rendered-dom-and-runtime",
            status="BLOCKED",
            observed_at=utc_now(),
            target=redacted,
            details={
                "suite": suite_name,
                "case_name": "Pillar 8 — Post-JS SPA Rendered DOM & Browser Runtime Audit",
                "tags": ["web", "browser", "a11y", "js"],
                "http_method": "GET",
                "status_code": 0,
                "elapsed_ms": float(info.get("wall_ms") or 0.0),
                "failure_reasons": ["No headless browser runtime available for SPA DOM execution"],
            },
        )

    dom = _DomAuditParser()
    dom.feed(str(info.get("rendered_html") or ""))
    a11y_status, a11y_checks, a11y_failures, a11y_metrics = _audit_dom_accessibility(dom)

    checks_passed = [
        f"engine:{info['engine']}",
        f"rendered_nodes:{info['dom_node_count']}",
        f"links_rendered:{len(dom.links)}",
        f"buttons_rendered:{len(dom.buttons)}",
        *a11y_checks,
    ]
    failures = list(a11y_failures)
    if info.get("page_errors"):
        failures.append(f"{len(info['page_errors'])} uncaught JS pageerror(s): {info['page_errors'][0]}")
    if info.get("console_errors"):
        failures.append(f"{len(info['console_errors'])} browser console.error(s): {info['console_errors'][0]}")
    if info.get("failed_requests"):
        failures.append(f"{len(info['failed_requests'])} failed XHR/asset request(s): {info['failed_requests'][0]}")

    status = "FAIL" if failures else a11y_status
    return EvidenceRecord(
        test_id="pillar-8.spa-rendered-dom-and-runtime",
        status=status,
        observed_at=utc_now(),
        target=redacted,
        details={
            "suite": suite_name,
            "case_name": "Pillar 8 — Post-JS SPA Rendered DOM & Browser Runtime Audit",
            "tags": ["web", "browser", "a11y", "js"],
            "http_method": "GET",
            "status_code": 200,
            "elapsed_ms": float(info.get("wall_ms") or 0.0),
            "engine": info["engine"],
            "dom_node_count": info["dom_node_count"],
            "rendered_links_count": len(dom.links),
            "rendered_buttons_count": len(dom.buttons),
            "rendered_headings_count": len(dom.headings),
            "console_errors": info.get("console_errors", []),
            "page_errors": info.get("page_errors", []),
            "failed_requests": info.get("failed_requests", []),
            "navigation_timing": info.get("navigation_timing", {}),
            "checks_passed": checks_passed,
            "failure_reasons": failures,
            "rendered_a11y": a11y_metrics,
        },
    )

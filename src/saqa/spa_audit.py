"""Live SPA / Headless Browser DOM, Core Web Vitals, Multi-Viewport Responsive & Interactive Journey Auditor.

Covers:
- Pillar 8: Post-JS rendered DOM, console/page errors, failed XHRs, Core Web Vitals (FCP/LCP/CLS), & asset budgets.
- Responsive Multi-Viewport Audit: Desktop (1440x900), Tablet (768x1024), Mobile (390x844) horizontal overflow & tap targets.
- Interactive Browser UI Journeys: Declarative E2E flows (`goto`, `click`, `fill`, `wait_for_selector`, `assert_text`, `screenshot`)
  with authenticated `storage_state`, cookies, and custom headers.
"""
from __future__ import annotations

import json
import subprocess
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from .analytics import analyze_records
from .evidence import EvidenceRecord, utc_now, write_manifest
from .url_safety import redact_url
from .visual_evidence import DEFAULT_VIEWPORTS, _find_chromium_binary
from .web_audit import _audit_dom_accessibility, _DomAuditParser

_LCP_CLS_OBSERVER_INIT_JS = """(() => {
    window.__saqaVitals = { lcp_ms: null, cls: 0.0 };
    try {
        const lcpObs = new PerformanceObserver((list) => {
            const entries = list.getEntries();
            if (entries.length) {
                window.__saqaVitals.lcp_ms = Math.round(entries[entries.length - 1].startTime);
            }
        });
        lcpObs.observe({ type: 'largest-contentful-paint', buffered: true });
        window.__saqaLcpObs = lcpObs;
    } catch (e) {}
    try {
        const clsObs = new PerformanceObserver((list) => {
            for (const entry of list.getEntries()) {
                if (!entry.hadRecentInput && typeof entry.value === 'number') {
                    window.__saqaVitals.cls += entry.value;
                }
            }
        });
        clsObs.observe({ type: 'layout-shift', buffered: true });
        window.__saqaClsObs = clsObs;
    } catch (e) {}
})();"""

_CWV_AND_BUDGET_JS = """() => {
    const nav = performance.getEntriesByType('navigation')[0];
    const navTiming = nav ? {
        ttfb_ms: Math.round(nav.responseStart - nav.requestStart),
        dom_interactive_ms: Math.round(nav.domInteractive),
        load_event_ms: Math.round(nav.loadEventEnd)
    } : {};

    if (window.__saqaLcpObs && typeof window.__saqaLcpObs.takeRecords === 'function') {
        const pendingLcp = window.__saqaLcpObs.takeRecords() || [];
        if (pendingLcp.length) {
            window.__saqaVitals.lcp_ms = Math.round(pendingLcp[pendingLcp.length - 1].startTime);
        }
    }
    if (window.__saqaClsObs && typeof window.__saqaClsObs.takeRecords === 'function') {
        for (const entry of (window.__saqaClsObs.takeRecords() || [])) {
            if (!entry.hadRecentInput && typeof entry.value === 'number') {
                window.__saqaVitals.cls += entry.value;
            }
        }
    }
    const fcpEntry = performance.getEntriesByName('first-contentful-paint')[0];
    const lcpEntries = performance.getEntriesByType('largest-contentful-paint') || [];
    const clsEntries = performance.getEntriesByType('layout-shift') || [];
    let clsScore = (window.__saqaVitals && typeof window.__saqaVitals.cls === 'number') ? window.__saqaVitals.cls : 0.0;
    if (clsScore === 0.0) {
        for (const entry of clsEntries) {
            if (!entry.hadRecentInput && typeof entry.value === 'number') {
                clsScore += entry.value;
            }
        }
    }
    const observedLcp = (window.__saqaVitals && window.__saqaVitals.lcp_ms != null)
        ? window.__saqaVitals.lcp_ms
        : (lcpEntries.length ? Math.round(lcpEntries[lcpEntries.length - 1].startTime) : null);

    const vitals = {
        fcp_ms: fcpEntry ? Math.round(fcpEntry.startTime) : null,
        lcp_ms: observedLcp,
        cls: Math.round(clsScore * 10000) / 10000
    };

    const resources = performance.getEntriesByType('resource') || [];
    let scriptBytes = 0, styleBytes = 0, imgBytes = 0, totalBytes = 0;
    for (const r of resources) {
        const sz = r.transferSize || r.encodedBodySize || 0;
        totalBytes += sz;
        if (r.initiatorType === 'script') scriptBytes += sz;
        else if (r.initiatorType === 'link' || r.initiatorType === 'css') styleBytes += sz;
        else if (r.initiatorType === 'img') imgBytes += sz;
    }

    // WCAG 2.2 AA Color Contrast Audit (4.5:1 normal text, 3.0:1 large text)
    function parseRgb(str) {
        const m = String(str || '').match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)(?:,\\s*([\\d.]+))?\\)/);
        if (!m) return null;
        return [Number(m[1]), Number(m[2]), Number(m[3]), m[4] === undefined ? 1 : Number(m[4])];
    }
    function relLum(rgb) {
        const vals = rgb.slice(0, 3).map(v => {
            const c = v / 255;
            return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
        });
        return 0.2126 * vals[0] + 0.7152 * vals[1] + 0.0722 * vals[2];
    }
    function effectiveBg(el) {
        let cur = el;
        while (cur && cur.nodeType === 1) {
            const cs = getComputedStyle(cur);
            if (cs.backgroundImage && cs.backgroundImage !== 'none') return null;
            const bg = parseRgb(cs.backgroundColor);
            if (bg && bg[3] > 0.15) return bg;
            cur = cur.parentElement;
        }
        return [255, 255, 255, 1];
    }
    let contrastChecked = 0;
    const lowContrastSamples = [];
    const textEls = document.querySelectorAll('h1, h2, h3, p, a, button, label');
    for (const el of textEls) {
        if (contrastChecked >= 100) break;
        const txt = (el.textContent || '').trim();
        if (!txt || txt.length < 2) continue;
        const rect = el.getBoundingClientRect();
        if (rect.width < 4 || rect.height < 4) continue;
        const st = getComputedStyle(el);
        if (st.visibility === 'hidden' || st.display === 'none' || Number(st.opacity) < 0.2) continue;
        const fg = parseRgb(st.color);
        if (!fg || fg[3] < 0.2) continue;
        const bg = effectiveBg(el);
        if (!bg) continue;
        const l1 = relLum(fg), l2 = relLum(bg);
        const ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
        const fontSize = parseFloat(st.fontSize) || 14;
        const isBold = parseInt(st.fontWeight, 10) >= 700;
        const minRatio = (fontSize >= 24 || (fontSize >= 18.66 && isBold)) ? 3.0 : 4.5;
        contrastChecked += 1;
        if (ratio < minRatio && lowContrastSamples.length < 5) {
            lowContrastSamples.push(`${el.tagName.toLowerCase()}("${txt.slice(0, 24)}")=${ratio.toFixed(2)}:1<${minRatio}:1`);
        }
    }

    return {
        navigation_timing: navTiming,
        web_vitals: vitals,
        asset_budget: {
            resource_count: resources.length,
            total_bytes: totalBytes,
            script_bytes: scriptBytes,
            style_bytes: styleBytes,
            image_bytes: imgBytes
        },
        contrast_audit: {
            checked: contrastChecked,
            low_contrast_count: lowContrastSamples.length,
            samples: lowContrastSamples
        }
    };
}"""


def _validate_http_url(url: str, label: str = "SPA audit") -> None:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"invalid {label} URL: {url!r}")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"{label} URL must not contain embedded credentials")


def inspect_spa_runtime(
    url: str,
    *,
    timeout_s: int = 25,
    extra_headers: Mapping[str, str] | None = None,
    storage_state: Path | str | None = None,
) -> dict[str, Any]:
    """Execute a live headless browser render to audit post-JS DOM, console errors, Core Web Vitals, and asset budgets."""
    _validate_http_url(url, "SPA audit")

    # 1. Prefer full Playwright telemetry (console errors, pageerrors, failed requests, Core Web Vitals, asset budgets)
    try:
        from playwright.sync_api import sync_playwright

        console_errors: list[str] = []
        page_errors: list[str] = []
        failed_requests: list[str] = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                ctx_kwargs: dict[str, Any] = {"viewport": {"width": 1440, "height": 900}}
                if extra_headers:
                    ctx_kwargs["extra_http_headers"] = dict(extra_headers)
                if storage_state is not None and Path(storage_state).is_file():
                    ctx_kwargs["storage_state"] = str(storage_state)
                context = browser.new_context(**ctx_kwargs)
                if hasattr(context, "add_init_script"):
                    context.add_init_script(_LCP_CLS_OBSERVER_INIT_JS)
                page = context.new_page()
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
                perf_payload = page.evaluate(_CWV_AND_BUDGET_JS) or {}
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
                    "navigation_timing": perf_payload.get("navigation_timing", {}),
                    "web_vitals": perf_payload.get("web_vitals", {}),
                    "asset_budget": perf_payload.get("asset_budget", {}),
                    "contrast_audit": perf_payload.get("contrast_audit", {}),
                }
            finally:
                browser.close()
    except Exception:  # noqa: S110
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
            "web_vitals": {},
            "asset_budget": {},
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
    completed = subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_s,
    )
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
            "web_vitals": {},
            "asset_budget": {},
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
        "web_vitals": {},
        "asset_budget": {"rendered_html_bytes": len(rendered_html.encode("utf-8"))},
    }


def build_spa_audit_record(
    target_url: str,
    *,
    suite_name: str,
    timeout_s: int = 25,
    inspector=None,
    extra_headers: Mapping[str, str] | None = None,
    storage_state: Path | str | None = None,
) -> EvidenceRecord:
    """Run Pillar 8 SPA post-JS render & Core Web Vitals audit and return a canonical EvidenceRecord."""
    active_inspector = inspector or inspect_spa_runtime
    redacted = redact_url(target_url)
    call_kwargs: dict[str, Any] = {"timeout_s": timeout_s}
    if extra_headers is not None:
        call_kwargs["extra_headers"] = extra_headers
    if storage_state is not None:
        call_kwargs["storage_state"] = storage_state
    try:
        info = active_inspector(target_url, **call_kwargs)
    except TypeError:
        info = active_inspector(target_url, timeout_s=timeout_s)

    if not info.get("available"):
        return EvidenceRecord(
            test_id="pillar-8.spa-rendered-dom-and-runtime",
            status="BLOCKED",
            observed_at=utc_now(),
            target=redacted,
            details={
                "suite": suite_name,
                "case_name": "Pillar 8 — Post-JS SPA Rendered DOM, Core Web Vitals & Runtime Audit",
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
    vitals = info.get("web_vitals") or {}
    if vitals.get("fcp_ms") is not None:
        checks_passed.append(f"fcp_ms:{vitals['fcp_ms']}")
    if vitals.get("lcp_ms") is not None:
        checks_passed.append(f"lcp_ms:{vitals['lcp_ms']}")
    if vitals.get("cls") is not None:
        checks_passed.append(f"cls:{vitals['cls']}")

    failures = list(a11y_failures)
    warnings = list(a11y_metrics.get("warnings") or [])
    if vitals.get("cls") is not None and float(vitals["cls"]) > 0.25:
        failures.append(f"Core Web Vitals CLS {vitals['cls']} exceeds poor threshold (0.25)")
    elif vitals.get("cls") is not None and float(vitals["cls"]) > 0.1:
        warnings.append(f"Core Web Vitals CLS {vitals['cls']} needs improvement (> 0.10)")

    if info.get("page_errors"):
        failures.append(f"{len(info['page_errors'])} uncaught JS pageerror(s): {info['page_errors'][0]}")
    if info.get("console_errors"):
        failures.append(f"{len(info['console_errors'])} browser console.error(s): {info['console_errors'][0]}")
    if info.get("failed_requests"):
        failures.append(f"{len(info['failed_requests'])} failed XHR/asset request(s): {info['failed_requests'][0]}")
    contrast = info.get("contrast_audit") or {}
    if int(contrast.get("checked", 0)) > 0:
        checks_passed.append(f"wcag_contrast_checked:{contrast['checked']}")
    if int(contrast.get("low_contrast_count", 0)) > 0:
        samples_txt = ", ".join(contrast.get("samples", [])[:3])
        warnings.append(f"WCAG 2.2 AA low color contrast detected ({contrast['low_contrast_count']} sample(s)): {samples_txt}")

    status = "FAIL" if failures else a11y_status
    return EvidenceRecord(
        test_id="pillar-8.spa-rendered-dom-and-runtime",
        status=status,
        observed_at=utc_now(),
        target=redacted,
        details={
            "suite": suite_name,
            "case_name": "Pillar 8 — Post-JS SPA Rendered DOM, Core Web Vitals & Runtime Audit",
            "tags": ["web", "browser", "a11y", "js"],
            "http_method": "GET",
            "status_code": 200,
            "elapsed_ms": float(info.get("wall_ms") or 0.0),
            "engine": info["engine"],
            "dom_node_count": info["dom_node_count"],
            "rendered_links_count": len(dom.links),
            "rendered_links": [str(lnk["href"]) for lnk in dom.links if lnk.get("href")][:100],
            "rendered_buttons_count": len(dom.buttons),
            "rendered_headings_count": len(dom.headings),
            "console_errors": info.get("console_errors", []),
            "page_errors": info.get("page_errors", []),
            "failed_requests": info.get("failed_requests", []),
            "navigation_timing": info.get("navigation_timing", {}),
            "web_vitals": vitals,
            "asset_budget": info.get("asset_budget", {}),
            "contrast_audit": contrast,
            "checks_passed": checks_passed,
            "failure_reasons": failures,
            "warnings": warnings,
            "rendered_a11y": a11y_metrics,
        },
    )


def inspect_spa_subpages(
    urls: Sequence[str],
    *,
    timeout_s: int = 20,
    extra_headers: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Render multiple internal SPA subpages in one shared headless Playwright browser to check post-JS DOM & JS errors."""
    if not urls:
        return []
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return []

    results: list[dict[str, Any]] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            ctx_kwargs: dict[str, Any] = {"viewport": {"width": 1440, "height": 900}}
            if extra_headers:
                ctx_kwargs["extra_http_headers"] = dict(extra_headers)
            context = browser.new_context(**ctx_kwargs)
            page = context.new_page()
            active_c_errs: list[str] = []
            active_p_errs: list[str] = []
            page.on(
                "console",
                lambda msg: active_c_errs.append(msg.text[:180]) if msg.type == "error" else None,
            )
            page.on("pageerror", lambda err: active_p_errs.append(str(err)[:180]))
            for u in urls:
                _validate_http_url(u, "SPA subpage")
                active_c_errs.clear()
                active_p_errs.clear()
                t0 = time.perf_counter()
                try:
                    resp = page.goto(u, wait_until="networkidle", timeout=timeout_s * 1000)
                    status_code = resp.status if resp is not None else 200
                    html_str = page.content()
                except Exception as exc:
                    status_code = 0
                    html_str = ""
                    active_p_errs.append(str(exc)[:180])
                results.append({
                    "url": u,
                    "status_code": status_code,
                    "elapsed_ms": round((time.perf_counter() - t0) * 1000, 2),
                    "rendered_html": html_str,
                    "console_errors": list(active_c_errs[:5]),
                    "page_errors": list(active_p_errs[:5]),
                })
            context.close()
        finally:
            browser.close()
    return results


def inspect_responsive_viewports(
    url: str,
    *,
    viewports: Sequence[tuple[str, int, int]] = DEFAULT_VIEWPORTS,
    timeout_s: int = 25,
) -> dict[str, Any]:
    """Audit Desktop, Tablet, and Mobile viewports for horizontal overflow & mobile tap-target usability."""
    _validate_http_url(url, "responsive audit")
    t0 = time.perf_counter()

    try:
        from playwright.sync_api import sync_playwright

        matrix: list[dict[str, Any]] = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                for label, width, height in viewports:
                    context = browser.new_context(
                        viewport={"width": width, "height": height},
                        is_mobile=(width <= 480),
                        has_touch=(width <= 820),
                    )
                    page = context.new_page()
                    page.goto(url, wait_until="networkidle", timeout=timeout_s * 1000)
                    metrics = page.evaluate(
                        """(isMobile) => {
                            const docW = document.documentElement ? document.documentElement.scrollWidth : 0;
                            const winW = window.innerWidth || 1;
                            const overflowPx = Math.max(0, docW - winW);
                            let smallTapTargets = 0;
                            if (isMobile) {
                                const els = document.querySelectorAll('button, a[href], input, select');
                                for (const el of els) {
                                    const r = el.getBoundingClientRect();
                                    if (r.width > 0 && r.height > 0 && (r.width < 24 || r.height < 24)) {
                                        smallTapTargets += 1;
                                    }
                                }
                            }
                            return { overflow_px: overflowPx, small_tap_targets: smallTapTargets };
                        }""",
                        width <= 480,
                    )
                    matrix.append({
                        "viewport": label,
                        "width": width,
                        "height": height,
                        "overflow_px": int(metrics.get("overflow_px", 0)),
                        "small_tap_targets": int(metrics.get("small_tap_targets", 0)),
                        "rendered": True,
                    })
                    context.close()
                return {
                    "engine": "playwright-chromium",
                    "available": True,
                    "wall_ms": round((time.perf_counter() - t0) * 1000, 2),
                    "viewports": matrix,
                }
            finally:
                browser.close()
    except Exception:  # noqa: S110
        pass

    binary = _find_chromium_binary()
    if not binary:
        return {"engine": "none", "available": False, "wall_ms": 0.0, "viewports": []}

    matrix_fb: list[dict[str, Any]] = []
    for label, width, height in viewports:
        cmd = [
            binary,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            f"--window-size={width},{height}",
            "--virtual-time-budget=3500",
            "--dump-dom",
            url,
        ]
        completed = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
        )
        ok = completed.returncode == 0 and "<html" in (completed.stdout or "").lower()
        matrix_fb.append({
            "viewport": label,
            "width": width,
            "height": height,
            "overflow_px": 0,
            "small_tap_targets": 0,
            "rendered": ok,
        })
    return {
        "engine": "chromium-dump-dom",
        "available": any(v["rendered"] for v in matrix_fb),
        "wall_ms": round((time.perf_counter() - t0) * 1000, 2),
        "viewports": matrix_fb,
    }


def build_responsive_audit_record(
    target_url: str,
    *,
    suite_name: str,
    timeout_s: int = 25,
    inspector=None,
) -> EvidenceRecord:
    """Build EvidenceRecord for Multi-Viewport (Desktop/Tablet/Mobile) Responsive Layout & Tap-Target QA."""
    active_inspector = inspector or inspect_responsive_viewports
    redacted = redact_url(target_url)
    info = active_inspector(target_url, timeout_s=timeout_s)
    if not info.get("available"):
        return EvidenceRecord(
            test_id="responsive.multi-viewport-matrix",
            status="BLOCKED",
            observed_at=utc_now(),
            target=redacted,
            details={
                "suite": suite_name,
                "case_name": "Responsive Multi-Viewport Matrix (Desktop / Tablet / Mobile)",
                "tags": ["web", "browser", "responsive", "mobile", "a11y"],
                "http_method": "GET",
                "status_code": 0,
                "elapsed_ms": float(info.get("wall_ms") or 0.0),
                "failure_reasons": ["No headless browser available for multi-viewport inspection"],
            },
        )

    checks_passed: list[str] = [f"engine:{info['engine']}"]
    failures: list[str] = []
    warnings: list[str] = []
    for vp in info.get("viewports") or []:
        name = vp["viewport"]
        if not vp.get("rendered"):
            failures.append(f"Viewport {name} ({vp['width']}x{vp['height']}) failed to render")
            continue
        checks_passed.append(f"viewport_ok:{name}({vp['width']}x{vp['height']})")
        if int(vp.get("overflow_px", 0)) > 8:
            failures.append(f"Horizontal layout overflow on {name} ({vp['width']}px): +{vp['overflow_px']}px")
        if int(vp.get("small_tap_targets", 0)) > 0:
            warnings.append(f"{vp['small_tap_targets']} interactive control(s) on {name} smaller than 24x24px (WCAG 2.5.8)")

    return EvidenceRecord(
        test_id="responsive.multi-viewport-matrix",
        status="FAIL" if failures else "PASS",
        observed_at=utc_now(),
        target=redacted,
        details={
            "suite": suite_name,
            "case_name": "Responsive Multi-Viewport Matrix (Desktop / Tablet / Mobile)",
            "tags": ["web", "browser", "responsive", "mobile", "a11y"],
            "http_method": "GET",
            "status_code": 200,
            "elapsed_ms": float(info.get("wall_ms") or 0.0),
            "viewports": info.get("viewports", []),
            "checks_passed": checks_passed,
            "failure_reasons": failures,
            "warnings": warnings,
        },
    )


def load_journey_file(path: Path) -> dict[str, Any]:
    """Load and validate a declarative browser UI journey JSON file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("journeys"), list) or not data["journeys"]:
        raise ValueError("Browser journey file must be a JSON object with a non-empty 'journeys' list")
    return data


def run_browser_journey(
    journey_spec: Mapping[str, Any],
    *,
    output_dir: Path | None = None,
) -> tuple[list[EvidenceRecord], dict[str, Any]]:
    """Execute declarative interactive browser user journeys (with optional auth storage_state/cookies/headers)."""
    suite_name = str(journey_spec.get("name") or "saqa-browser-journey")
    base_url = str(journey_spec.get("base_url") or "").rstrip("/")
    viewport = journey_spec.get("viewport") or {"width": 1440, "height": 900}
    extra_headers = journey_spec.get("headers") or {}
    cookies = journey_spec.get("cookies") or []
    storage_state = journey_spec.get("storage_state")
    journeys = journey_spec.get("journeys") or []
    if not journeys:
        raise ValueError("journey_spec must define at least one journey in 'journeys'")

    records: list[EvidenceRecord] = []
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        for j in journeys:
            jid = str(j.get("id") or "journey")
            records.append(
                EvidenceRecord(
                    test_id=jid,
                    status="BLOCKED",
                    observed_at=utc_now(),
                    target=redact_url(base_url or "browser://local"),
                    details={
                        "suite": suite_name,
                        "case_name": str(j.get("name") or jid),
                        "tags": ["web", "browser", "journey"],
                        "http_method": "GET",
                        "status_code": 0,
                        "elapsed_ms": 0.0,
                        "failure_reasons": ["Playwright is required to execute interactive multi-step browser journeys"],
                    },
                )
            )
        analytics = analyze_records(records)
        return records, analytics

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for j in journeys:
                jid = str(j.get("id") or "journey")
                jname = str(j.get("name") or jid)
                steps = j.get("steps") or []
                ctx_kwargs: dict[str, Any] = {
                    "viewport": {"width": int(viewport.get("width", 1440)), "height": int(viewport.get("height", 900))},
                    "reduced_motion": "reduce",
                }
                if extra_headers:
                    ctx_kwargs["extra_http_headers"] = dict(extra_headers)
                if storage_state and Path(str(storage_state)).is_file():
                    ctx_kwargs["storage_state"] = str(storage_state)
                if j.get("user_agent"):
                    ctx_kwargs["user_agent"] = str(j["user_agent"])

                context = browser.new_context(**ctx_kwargs)
                if cookies:
                    context.add_cookies(list(cookies))
                page = context.new_page()

                t0 = time.perf_counter()
                checks_passed: list[str] = []
                failures: list[str] = []
                current_target = base_url or "about:blank"

                try:
                    for idx, step in enumerate(steps, start=1):
                        action = str(step.get("action") or "").strip().lower()
                        if action == "goto":
                            raw_u = str(step["url"])
                            full_u = raw_u if raw_u.startswith(("http://", "https://")) else f"{base_url}/{raw_u.lstrip('/')}"
                            _validate_http_url(full_u, "journey goto")
                            current_target = full_u
                            page.goto(full_u, wait_until="networkidle", timeout=int(step.get("timeout_ms", 20000)))
                            checks_passed.append(f"step_{idx}:goto")
                        elif action == "wait_for_selector":
                            raw_st = str(step.get("state", "visible")).lower()
                            wait_state: Literal["attached", "detached", "hidden", "visible"] = (
                                "attached"
                                if raw_st == "attached"
                                else ("detached" if raw_st == "detached" else ("hidden" if raw_st == "hidden" else "visible"))
                            )
                            page.wait_for_selector(str(step["selector"]), state=wait_state, timeout=int(step.get("timeout_ms", 10000)))
                            checks_passed.append(f"step_{idx}:wait({step['selector']})")
                        elif action == "click":
                            page.click(str(step["selector"]), timeout=int(step.get("timeout_ms", 10000)))
                            checks_passed.append(f"step_{idx}:click({step['selector']})")
                        elif action == "fill":
                            page.fill(str(step["selector"]), str(step.get("value", "")), timeout=int(step.get("timeout_ms", 10000)))
                            checks_passed.append(f"step_{idx}:fill({step['selector']})")
                        elif action == "press":
                            page.press(str(step["selector"]), str(step["key"]), timeout=int(step.get("timeout_ms", 10000)))
                            checks_passed.append(f"step_{idx}:press({step['key']})")
                        elif action == "scroll":
                            sx, sy = int(step.get("x", 0)), int(step.get("y", 600))
                            page.evaluate("([x, y]) => window.scrollTo(x, y)", [sx, sy])
                            checks_passed.append(f"step_{idx}:scroll({sx},{sy})")
                        elif action == "assert_text":
                            sel = str(step.get("selector") or "body")
                            expected = str(step["contains"])
                            actual = page.inner_text(sel, timeout=int(step.get("timeout_ms", 10000)))
                            if expected not in actual:
                                failures.append(f"Step #{idx} assert_text failed: {expected!r} not found in {sel!r}")
                                break
                            checks_passed.append(f"step_{idx}:assert_text")
                        elif action == "assert_visible":
                            sel = str(step["selector"])
                            if not page.is_visible(sel):
                                failures.append(f"Step #{idx} assert_visible failed: {sel!r} is not visible")
                                break
                            checks_passed.append(f"step_{idx}:assert_visible({sel})")
                        elif action == "assert_url":
                            expected_sub = str(step["contains"])
                            if expected_sub not in page.url:
                                failures.append(f"Step #{idx} assert_url failed: {expected_sub!r} not in {redact_url(page.url)!r}")
                                break
                            checks_passed.append(f"step_{idx}:assert_url")
                        elif action == "screenshot" and output_dir is not None:
                            output_dir.mkdir(parents=True, exist_ok=True)
                            sname = str(step.get("name") or f"{jid}-step-{idx}.png")
                            if not sname.endswith(".png"):
                                sname += ".png"
                            page.screenshot(path=str(output_dir / sname), animations="disabled")
                            checks_passed.append(f"step_{idx}:screenshot({sname})")
                        else:
                            raise ValueError(f"Unsupported browser journey action: {action!r}")
                except Exception as exc:
                    failures.append(f"Journey execution error: {exc}")
                finally:
                    wall_ms = round((time.perf_counter() - t0) * 1000, 2)
                    context.close()

                records.append(
                    EvidenceRecord(
                        test_id=jid,
                        status="FAIL" if failures else "PASS",
                        observed_at=utc_now(),
                        target=redact_url(current_target),
                        details={
                            "suite": suite_name,
                            "case_name": jname,
                            "tags": list(j.get("tags") or ["web", "browser", "journey"]),
                            "http_method": "GET",
                            "status_code": 200 if not failures else 500,
                            "elapsed_ms": wall_ms,
                            "checks_passed": checks_passed,
                            "failure_reasons": failures,
                        },
                    )
                )
        finally:
            browser.close()

    manifest_sha: str | None = None
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        manifest_sha = write_manifest(records, output_dir / "evidence-manifest.json")
    analytics = analyze_records(records, manifest_sha256=manifest_sha)
    if output_dir is not None:
        (output_dir / "suite-summary.json").write_text(
            json.dumps({"suite_name": suite_name, "analytics": analytics}, indent=2),
            encoding="utf-8",
        )
    return records, analytics

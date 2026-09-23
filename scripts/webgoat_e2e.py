"""Deterministic, read-only Playwright smoke for the local OWASP WebGoat target."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

BASE_URL = os.getenv("SAQA_WEBGOAT_URL", "http://127.0.0.1:8080/WebGoat/")
BROWSER = os.getenv("SAQA_BROWSER", "chromium").lower()
ALLOWED_BROWSERS = {"chromium", "firefox", "webkit"}
LOOPBACK_HOSTS = {"127.0.0.1", "localhost"}
ARTIFACT = Path("artifacts/targets") / f"webgoat-e2e-{BROWSER}.json"


def validate_target(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in LOOPBACK_HOSTS or parsed.username or parsed.password or parsed.port is None:
        raise ValueError("WebGoat E2E target must be credential-free HTTP on an approved loopback host with a port")


def guard_request(route) -> None:
    parsed = urlparse(route.request.url)
    if route.request.method != "GET":
        route.abort()
        return
    base = urlparse(BASE_URL)
    try:
        parsed_port = parsed.port
    except ValueError:
        parsed_port = None
    if parsed.scheme != base.scheme or parsed.hostname != base.hostname or parsed_port != base.port or parsed.username or parsed.password:
        route.abort()
        raise RuntimeError(f"blocked non-loopback WebGoat request: {route.request.url!r}")
    route.continue_()


def main() -> None:
    from playwright.sync_api import sync_playwright

    validate_target(BASE_URL)
    if BROWSER not in ALLOWED_BROWSERS:
        raise ValueError(f"unsupported browser: {BROWSER}")

    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    evidence = {
        "schema": "saqa.webgoat-e2e.v3",
        "test_id": f"webgoat.e2e.{BROWSER}.smoke",
        "target": BASE_URL,
        "browser": BROWSER,
        "http_methods": ["GET"],
        "redirects_followed": "guarded",
        "destructive_actions": False,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "status": "FAIL",
        "details": {},
    }

    started = time.perf_counter()
    browser = None
    try:
        with sync_playwright() as playwright:
            browser = getattr(playwright, BROWSER).launch(headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 900})
            context.route("**/*", guard_request)
            page = context.new_page()
            response = page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30_000)
            validate_target(page.url)
            if response is None or response.status >= 400:
                raise RuntimeError(f"WebGoat page load failed: HTTP {response.status if response else 'none'}")
            page.wait_for_load_state("networkidle", timeout=30_000)
            title = page.title().strip()
            final_url = page.url
            parsed_final = urlparse(final_url)
            if parsed_final.hostname not in LOOPBACK_HOSTS:
                raise AssertionError(f"unexpected final host: {parsed_final.hostname!r}")
            if "/WebGoat" not in parsed_final.path:
                raise AssertionError(f"unexpected final path: {parsed_final.path!r}")
            if not title or title.lower() not in {"login page", "webgoat"}:
                raise AssertionError(f"unexpected page title: {title!r}")
            body_text = page.locator("body").inner_text().strip()
            if not body_text:
                raise AssertionError("WebGoat page body is empty")
            evidence["status"] = "PASS"
            evidence["details"] = {
                "title": title,
                "final_url": final_url,
                "http_status": response.status,
                "body_text_nonempty": True,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
            }
            context.close()
    except Exception as exc:
        evidence["details"] = {
            **evidence.get("details", {}),
            "error": f"{type(exc).__name__}: {exc}",
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        }
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception as exc:
                evidence["details"]["browser_close_error"] = f"{type(exc).__name__}: {exc}"
        ARTIFACT.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps(evidence, indent=2, sort_keys=True))
    if evidence["status"] != "PASS":
        raise RuntimeError("WebGoat E2E smoke failed; evidence recorded as FAIL")


if __name__ == "__main__":
    main()

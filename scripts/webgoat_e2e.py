"""Deterministic, read-only Playwright smoke for the local OWASP WebGoat target."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

BASE_URL = os.getenv("SAQA_WEBGOAT_URL", "http://127.0.0.1:8080/WebGoat/")
BROWSER = os.getenv("SAQA_BROWSER", "chromium").lower()
ALLOWED_BROWSERS = {"chromium", "firefox", "webkit"}
ARTIFACT = Path("artifacts/targets") / f"webgoat-e2e-{BROWSER}.json"


def validate_target(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("WebGoat E2E target must be local HTTP loopback")


def main() -> None:
    validate_target(BASE_URL)
    if BROWSER not in ALLOWED_BROWSERS:
        raise ValueError(f"unsupported browser: {BROWSER}")

    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    evidence = {
        "schema": "saqa.webgoat-e2e.v1",
        "test_id": f"webgoat.e2e.{BROWSER}.smoke",
        "target": BASE_URL,
        "browser": BROWSER,
        "http_methods": ["GET"],
        "destructive_actions": False,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "status": "FAIL",
        "details": {},
    }

    started = time.perf_counter()
    try:
        with sync_playwright() as playwright:
            browser = getattr(playwright, BROWSER).launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                response = page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30_000)
                if response is None or response.status >= 400:
                    raise RuntimeError(f"WebGoat page load failed: HTTP {response.status if response else 'none'}")
                page.wait_for_load_state("networkidle", timeout=30_000)
                title = page.title()
                body_text = page.locator("body").inner_text().strip()
                if "webgoat" not in title.lower():
                    raise AssertionError(f"unexpected page title: {title!r}")
                if not body_text:
                    raise AssertionError("WebGoat page body is empty")
                evidence["status"] = "PASS"
                evidence["details"] = {
                    "title": title,
                    "final_url": page.url,
                    "http_status": response.status,
                    "body_text_nonempty": True,
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                }
            finally:
                browser.close()
    finally:
        if not evidence["details"]:
            evidence["details"] = {"elapsed_ms": round((time.perf_counter() - started) * 1000, 2)}
        ARTIFACT.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if evidence["status"] != "PASS":
        raise RuntimeError("WebGoat E2E smoke failed; evidence recorded as FAIL")


if __name__ == "__main__":
    main()

"""Read-only mobile viewport readiness smoke for the local OWASP Juice Shop target."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

BASE_URL = os.getenv("SAQA_MOBILE_BASE_URL", "http://127.0.0.1:3000").rstrip("/")
BROWSER = os.getenv("SAQA_BROWSER", "chromium").lower()
OUTPUT = Path("artifacts/targets/juice-shop-mobile-readiness.json")
ALLOWED_BROWSERS = {"chromium", "firefox", "webkit"}


def _assert_loopback_http(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("mobile target must be local HTTP loopback only")


def main() -> None:
    _assert_loopback_http(BASE_URL)
    if BROWSER not in ALLOWED_BROWSERS:
        raise ValueError(f"unsupported browser: {BROWSER}")

    from playwright.sync_api import sync_playwright

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    evidence = {
        "schema": "saqa.juice-shop-mobile-readiness.v1",
        "test_id": f"juice-shop.mobile-readiness.{BROWSER}",
        "status": "FAIL",
        "target": BASE_URL,
        "browser": BROWSER,
        "viewport": {"width": 390, "height": 844, "device_scale_factor": 1},
        "http_methods": ["GET"],
        "destructive_actions": False,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "details": {},
    }

    try:
        with sync_playwright() as playwright:
            browser_type = getattr(playwright, BROWSER)
            browser = browser_type.launch(headless=True)
            page = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=1)
            response = page.goto(BASE_URL + "/", wait_until="domcontentloaded", timeout=15000)
            page.locator("app-root").wait_for(timeout=15000)
            title = page.title()
            body_text = page.locator("body").inner_text().strip()
            horizontal_overflow = page.evaluate(
                "() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1"
            )
            evidence["details"] = {
                "status_code": response.status if response else None,
                "title": title,
                "body_text_non_empty": bool(body_text),
                "horizontal_overflow": bool(horizontal_overflow),
            }
            if not response or response.status < 200 or response.status >= 400:
                raise AssertionError(f"expected successful page response, got {response.status if response else None}")
            if "Juice Shop" not in title:
                raise AssertionError(f"unexpected title: {title!r}")
            if not body_text:
                raise AssertionError("page body is empty")
            if horizontal_overflow:
                raise AssertionError("mobile viewport has horizontal document overflow")
            evidence["status"] = "PASS"
            browser.close()
    except Exception as exc:
        evidence["details"]["error"] = f"{type(exc).__name__}: {exc}"
        OUTPUT.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        raise

    OUTPUT.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()

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
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.username or parsed.password or parsed.port is None:
        raise ValueError("mobile target must be credential-free HTTP on 127.0.0.1 with a port")


def _guard_request(route) -> None:
    parsed = urlparse(route.request.url)
    base = urlparse(BASE_URL)
    if route.request.method != "GET":
        route.abort()
        return
    if parsed.scheme != base.scheme or parsed.hostname != base.hostname or parsed.port != base.port or parsed.username or parsed.password:
        route.abort()
        raise RuntimeError(f"blocked mobile request outside authorized target origin: {route.request.url!r}")
    route.continue_()


def main() -> None:
    _assert_loopback_http(BASE_URL)
    if BROWSER not in ALLOWED_BROWSERS:
        raise ValueError(f"unsupported browser: {BROWSER}")

    from playwright.sync_api import sync_playwright

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    evidence = {
        "schema": "saqa.juice-shop-mobile-readiness.v2",
        "test_id": f"juice-shop.mobile-readiness.{BROWSER}",
        "status": "FAIL",
        "target": BASE_URL,
        "browser": BROWSER,
        "viewport": {"width": 390, "height": 844, "device_scale_factor": 1},
        "http_methods": ["GET"],
        "redirects_followed": "guarded",
        "destructive_actions": False,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "details": {},
    }

    try:
        with sync_playwright() as playwright:
            browser = None
            context = None
            try:
                browser_type = getattr(playwright, BROWSER)
                browser = browser_type.launch(headless=True)
                context = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=1)
                context.route("**/*", _guard_request)
                page = context.new_page()
                response = page.goto(BASE_URL + "/", wait_until="domcontentloaded", timeout=15000)
                _assert_loopback_http(page.url)
                page.locator("app-root").wait_for(state="attached", timeout=15000)
                page.wait_for_function("document.body && document.body.innerText.trim().length > 0", timeout=15000)
                title = page.title()
                body_text = page.locator("body").inner_text().strip()
                horizontal_overflow = page.evaluate("() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1")
                evidence["details"] = {"status_code": response.status if response else None, "title": title, "body_text_non_empty": bool(body_text), "horizontal_overflow": bool(horizontal_overflow), "final_url": page.url}
                if not response or response.status < 200 or response.status >= 400:
                    raise AssertionError(f"expected successful page response, got {response.status if response else None}")
                if "Juice Shop" not in title:
                    raise AssertionError(f"unexpected title: {title!r}")
                if not body_text:
                    raise AssertionError("page body is empty")
                if horizontal_overflow:
                    raise AssertionError("mobile viewport has horizontal document overflow")
                context.close(); context = None
                browser.close(); browser = None
                evidence["status"] = "PASS"
            except Exception as exc:
                evidence["details"]["error"] = f"{type(exc).__name__}: {exc}"
                raise
            finally:
                if context is not None:
                    try: context.close()
                    except Exception: pass
                if browser is not None:
                    try: browser.close()
                    except Exception: pass
    except Exception as exc:
        evidence["details"]["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        OUTPUT.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps(evidence, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

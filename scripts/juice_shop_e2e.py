"""Deterministic, read-only Playwright E2E smoke for local OWASP Juice Shop."""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

BASE_URL = os.getenv("SAQA_JUICE_SHOP_URL", "http://127.0.0.1:3000").rstrip("/")
ARTIFACT_DIR = Path(os.getenv("SAQA_ARTIFACT_DIR", "artifacts/targets"))
BROWSER = os.getenv("SAQA_BROWSER", "chromium").lower()
SUPPORTED_BROWSERS = {"chromium", "firefox", "webkit"}


def _assert_loopback_http(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.username or parsed.password:
        raise ValueError("Juice Shop E2E target must be credential-free HTTP on 127.0.0.1")
    if parsed.port is None:
        raise ValueError("Juice Shop E2E target must specify a loopback port")


def _assert_local_request(request_url: str) -> None:
    parsed = urlparse(request_url)
    base = urlparse(BASE_URL)
    if (
        parsed.scheme != base.scheme
        or parsed.hostname != base.hostname
        or parsed.port != base.port
        or parsed.username
        or parsed.password
    ):
        raise RuntimeError(f"blocked browser request outside authorized target origin: {request_url!r}")


def main() -> int:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    evidence = {
        "schema": "saqa.juice-shop-e2e.v4",
        "test_id": f"juice-shop.e2e.{BROWSER}.smoke",
        "target": BASE_URL,
        "browser": BROWSER,
        "http_methods": ["GET"],
        "destructive_actions": False,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "status": "FAIL",
        "details": {},
    }
    browser = None
    context = None
    try:
        _assert_loopback_http(BASE_URL)
        if BROWSER not in SUPPORTED_BROWSERS:
            raise ValueError(f"unsupported SAQA_BROWSER: {BROWSER!r}")
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser_type = getattr(p, BROWSER)
            browser = browser_type.launch(headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 900})
            context.route(
                "**/*",
                lambda route: route.abort()
                if route.request.method != "GET"
                else (_assert_local_request(route.request.url), route.continue_())[1],
            )
            page = context.new_page()
            response = page.goto(BASE_URL + "/", wait_until="domcontentloaded", timeout=30_000)
            _assert_local_request(page.url)
            if response is None or not 200 <= response.status < 400:
                raise AssertionError(f"unexpected home response status: {response.status if response else None}")
            page.locator("app-root").wait_for(state="attached", timeout=15_000)
            title = page.title()
            if "Juice Shop" not in title:
                raise AssertionError(f"unexpected title: {title!r}")

            # Juice Shop uses Angular hash routing. Navigating the hash is a same-document
            # operation, so Playwright correctly returns no new HTTP Response for it.
            page.evaluate("window.location.hash = '#/search?q=apple'")
            page.wait_for_url(lambda url: url.startswith(BASE_URL + "/#/search?q=apple"), timeout=15_000)
            _assert_local_request(page.url)
            page.locator("app-root").wait_for(state="attached", timeout=15_000)
            final_url = page.url
            body_text = page.locator("body").inner_text(timeout=10_000)
            if "/#/search" not in final_url:
                raise AssertionError(f"unexpected search URL: {final_url!r}")
            if not body_text.strip():
                raise AssertionError("Juice Shop rendered an empty body")

            evidence["details"] = {
                "title": title,
                "home_status": response.status,
                "search_navigation": "same-document hash navigation",
                "final_url": final_url,
                "body_text_nonempty": True,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
            }
            context.close()
            context = None
            browser.close()
            browser = None
            evidence["status"] = "PASS"
    except Exception as exc:
        evidence["details"] = {
            **evidence.get("details", {}),
            "error": f"{type(exc).__name__}: {exc}",
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        }
    finally:
        if context is not None:
            try:
                context.close()
            except Exception as exc:
                evidence["details"]["context_close_error"] = f"{type(exc).__name__}: {exc}"
        if browser is not None:
            try:
                browser.close()
            except Exception as exc:
                evidence["details"]["browser_close_error"] = f"{type(exc).__name__}: {exc}"
        path = ARTIFACT_DIR / f"juice-shop-e2e-{BROWSER}.json"
        path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

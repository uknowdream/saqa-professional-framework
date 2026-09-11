"""Read-only accessibility readiness smoke for the local OWASP Juice Shop target."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

BASE_URL = os.getenv("SAQA_A11Y_BASE_URL", "http://127.0.0.1:3000").rstrip("/")
BROWSER = os.getenv("SAQA_BROWSER", "chromium").lower()
OUTPUT = Path("artifacts/targets/juice-shop-accessibility.json")
ALLOWED_BROWSERS = {"chromium", "firefox", "webkit"}


def _assert_loopback_http(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("accessibility target must be local HTTP loopback only")


def main() -> None:
    _assert_loopback_http(BASE_URL)
    if BROWSER not in ALLOWED_BROWSERS:
        raise ValueError(f"unsupported browser: {BROWSER}")

    from playwright.sync_api import sync_playwright

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    evidence = {
        "schema": "saqa.juice-shop-accessibility.v1",
        "test_id": f"juice-shop.accessibility-readiness.{BROWSER}",
        "status": "FAIL",
        "target": BASE_URL,
        "browser": BROWSER,
        "http_methods": ["GET"],
        "destructive_actions": False,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "details": {},
    }

    try:
        with sync_playwright() as playwright:
            browser_type = getattr(playwright, BROWSER)
            browser = browser_type.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            response = page.goto(BASE_URL + "/", wait_until="domcontentloaded", timeout=15000)
            page.locator("app-root").wait_for(state="attached", timeout=15000)
            page.wait_for_function("document.body && document.body.innerText.trim().length > 0", timeout=15000)

            metrics = page.evaluate(
                """() => {
                    const images = [...document.querySelectorAll('img')];
                    const controls = [...document.querySelectorAll('button, [role="button"], input, select, textarea')];
                    const headings = [...document.querySelectorAll('h1, h2, h3, h4, h5, h6')];
                    const landmarks = [...document.querySelectorAll('main, nav, header, footer, aside')];
                    const unnamedControls = controls.filter(el => {
                      if (el.hasAttribute('disabled')) return false;
                      const aria = (el.getAttribute('aria-label') || el.getAttribute('aria-labelledby') || '').trim();
                      const text = (el.innerText || el.value || el.getAttribute('title') || '').trim();
                      return !aria && !text;
                    });
                    const missingAlt = images.filter(img => !img.hasAttribute('alt'));
                    return {
                      lang_present: !!(document.documentElement.getAttribute('lang') || '').trim(),
                      title_present: !!(document.title || '').trim(),
                      image_count: images.length,
                      images_missing_alt: missingAlt.length,
                      interactive_control_count: controls.length,
                      unnamed_interactive_controls: unnamedControls.length,
                      heading_count: headings.length,
                      landmark_count: landmarks.length,
                    };
                }"""
            )
            evidence["details"] = {
                "status_code": response.status if response else None,
                **metrics,
            }
            if not response or response.status < 200 or response.status >= 400:
                raise AssertionError(f"expected successful page response, got {response.status if response else None}")
            failures = []
            if not metrics["lang_present"]:
                failures.append("document language is missing")
            if not metrics["title_present"]:
                failures.append("document title is missing")
            if metrics["images_missing_alt"]:
                failures.append(f"{metrics['images_missing_alt']} image(s) lack an alt attribute")
            if metrics["unnamed_interactive_controls"]:
                failures.append(f"{metrics['unnamed_interactive_controls']} interactive control(s) lack an accessible name")
            if failures:
                raise AssertionError("; ".join(failures))
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

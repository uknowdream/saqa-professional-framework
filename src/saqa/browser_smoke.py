"""Minimal browser readiness smoke used by the CI browser matrix."""
from __future__ import annotations

import os
import sys


ALLOWED = {"chromium", "firefox", "webkit"}


def _get_sync_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - depends on optional playwright install
        raise RuntimeError("Playwright is not installed. Install with: pip install playwright") from exc
    return sync_playwright


def main() -> int:
    browser_name = os.getenv("SAQA_BROWSER", "chromium")
    if browser_name not in ALLOWED:
        print(f"Unsupported SAQA_BROWSER={browser_name!r}", file=sys.stderr)
        return 2

    try:
        sync_playwright = _get_sync_playwright()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content("<html><head><title>SAQA</title></head><body>ready</body></html>")
            if page.title() != "SAQA" or page.locator("body").inner_text() != "ready":
                return 1
        finally:
            browser.close()
    print(f"{browser_name}: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

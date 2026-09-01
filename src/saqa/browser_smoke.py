"""Minimal browser readiness smoke used by the CI browser matrix."""

import os
import sys

from playwright.sync_api import sync_playwright


ALLOWED = {"chromium", "firefox", "webkit"}


def main() -> int:
    browser_name = os.getenv("SAQA_BROWSER", "chromium")
    if browser_name not in ALLOWED:
        print(f"Unsupported SAQA_BROWSER={browser_name!r}", file=sys.stderr)
        return 2

    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch(headless=True)
        page = browser.new_page()
        page.set_content("<html><head><title>SAQA</title></head><body>ready</body></html>")
        if page.title() != "SAQA" or page.locator("body").inner_text() != "ready":
            browser.close()
            return 1
        browser.close()
    print(f"{browser_name}: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

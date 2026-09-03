"""Deterministic, read-only Playwright E2E smoke for local OWASP Juice Shop."""

import json
import os
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_URL = os.getenv("SAQA_JUICE_SHOP_URL", "http://127.0.0.1:3000")
ARTIFACT_DIR = Path(os.getenv("SAQA_ARTIFACT_DIR", "artifacts/targets"))


def main() -> int:
    if not BASE_URL.startswith("http://127.0.0.1:"):
        raise SystemExit("Juice Shop E2E is restricted to loopback HTTP targets")

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    evidence = {
        "schema": "saqa.juice-shop-e2e.v1",
        "target": BASE_URL,
        "http_methods": ["GET"],
        "destructive_actions": False,
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(BASE_URL + "/", wait_until="domcontentloaded", timeout=30_000)
        page.locator("app-root").wait_for(state="attached", timeout=15_000)
        title = page.title()
        if "Juice Shop" not in title:
            raise AssertionError(f"unexpected title: {title!r}")

        page.goto(BASE_URL + "/#/search?q=apple", wait_until="domcontentloaded", timeout=30_000)
        page.locator("app-root").wait_for(state="attached", timeout=15_000)
        if "/#/search" not in page.url:
            raise AssertionError(f"unexpected search URL: {page.url!r}")
        body_text = page.locator("body").inner_text(timeout=10_000)
        if not body_text.strip():
            raise AssertionError("Juice Shop rendered an empty body")

        evidence.update(
            {
                "status": "PASS",
                "title": title,
                "final_url": page.url,
                "body_text_nonempty": True,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
            }
        )
        browser.close()

    path = ARTIFACT_DIR / "juice-shop-e2e.json"
    path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

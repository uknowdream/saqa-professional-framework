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
AXE_CORE_PATH = Path(os.getenv("SAQA_AXE_CORE_PATH", "node_modules/axe-core/axe.min.js"))
AXE_RULES = ["aria-input-field-name", "button-name", "link-name", "label"]


def _assert_loopback_http(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("accessibility target must be local HTTP loopback only")


def _load_axe_source() -> str:
    if not AXE_CORE_PATH.is_file():
        raise FileNotFoundError(f"axe-core oracle not found: {AXE_CORE_PATH}")
    return AXE_CORE_PATH.read_text(encoding="utf-8")


def _classify_heuristic_finding(unnamed_controls: list[dict[str, object]], oracle_violation_count: int) -> str:
    """Classify heuristic-only findings without silently converting uncertainty to green."""
    if not unnamed_controls:
        return "NONE"
    if oracle_violation_count:
        return "CONFIRMED_ORACLE"
    if all(int(control.get("tab_index", 0)) < 0 for control in unnamed_controls):
        return "FALSE_POSITIVE"
    return "INCONCLUSIVE"


def main() -> None:
    _assert_loopback_http(BASE_URL)
    if BROWSER not in ALLOWED_BROWSERS:
        raise ValueError(f"unsupported browser: {BROWSER}")

    from playwright.sync_api import sync_playwright

    axe_source = _load_axe_source()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    evidence = {
        "schema": "saqa.juice-shop-accessibility.v4",
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
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                response = page.goto(BASE_URL + "/", wait_until="domcontentloaded", timeout=15000)
                page.locator("app-root").wait_for(state="attached", timeout=15000)
                page.wait_for_function("document.body && document.body.innerText.trim().length > 0", timeout=15000)

                metrics = page.evaluate(
                    """() => {
                        const text = el => (el?.textContent || '').replace(/\\s+/g, ' ').trim();
                        const referencedText = el => {
                          const ids = (el.getAttribute('aria-labelledby') || '').split(/\\s+/).filter(Boolean);
                          return ids.map(id => document.getElementById(id)).map(text).filter(Boolean).join(' ');
                        };
                        const associatedLabel = el => {
                          if (el.id) {
                            const label = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
                            if (label) return text(label);
                          }
                          const parentLabel = el.closest('label');
                          return parentLabel ? text(parentLabel) : '';
                        };
                        const isRendered = el => {
                          if (el.getAttribute('aria-hidden') === 'true' || el.hidden) return false;
                          const style = getComputedStyle(el);
                          return style.display !== 'none' && style.visibility !== 'hidden';
                        };
                        const accessibleName = el => {
                          const ariaLabel = (el.getAttribute('aria-label') || '').trim();
                          if (ariaLabel) return ariaLabel;
                          const labelledBy = referencedText(el);
                          if (labelledBy) return labelledBy;
                          const label = associatedLabel(el);
                          if (label) return label;
                          const title = (el.getAttribute('title') || '').trim();
                          if (title) return title;
                          const tag = el.tagName.toLowerCase();
                          const type = (el.getAttribute('type') || '').toLowerCase();
                          if ((tag === 'input' && ['submit', 'reset', 'button', 'image'].includes(type))) {
                            const value = (el.getAttribute('value') || '').trim();
                            if (value) return value;
                            if (type === 'image') return (el.getAttribute('alt') || '').trim();
                          }
                          if (['button', 'a'].includes(tag) || el.getAttribute('role') === 'button' || el.getAttribute('role') === 'link') {
                            return text(el);
                          }
                          return '';
                        };
                        const images = [...document.querySelectorAll('img')].filter(isRendered);
                        const controls = [...document.querySelectorAll('button, a[href], input, select, textarea, [role="button"], [role="link"], [role="checkbox"], [role="radio"], [role="switch"], [role="combobox"], [role="textbox"], [role="menuitem"]')].filter(isRendered);
                        const unnamedControls = controls.filter(el => !accessibleName(el)).map(el => ({
                          tag: el.tagName.toLowerCase(),
                          id: el.id || '',
                          role: el.getAttribute('role') || '',
                          type: el.getAttribute('type') || '',
                          tab_index: el.tabIndex,
                          aria_hidden: el.getAttribute('aria-hidden') || '',
                          snippet: el.outerHTML.slice(0, 300)
                        }));
                        const headings = [...document.querySelectorAll('h1, h2, h3, h4, h5, h6')].filter(isRendered);
                        const landmarks = [...document.querySelectorAll('main, nav, header, footer, aside, [role="main"], [role="navigation"], [role="banner"], [role="contentinfo"]')].filter(isRendered);
                        const missingAlt = images.filter(img => !img.hasAttribute('alt'));
                        return {
                          lang_present: !!(document.documentElement.getAttribute('lang') || '').trim(),
                          title_present: !!(document.title || '').trim(),
                          image_count: images.length,
                          images_missing_alt: missingAlt.length,
                          interactive_control_count: controls.length,
                          unnamed_interactive_controls: unnamedControls.length,
                          unnamed_control_details: unnamedControls,
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

                page.add_script_tag(content=axe_source)
                oracle = page.evaluate(
                    """async rules => {
                      const result = await axe.run(document, { runOnly: { type: 'rule', values: rules } });
                      return {
                        violations: result.violations.map(v => ({
                          id: v.id,
                          impact: v.impact,
                          help: v.help,
                          nodes: v.nodes.map(n => ({ target: n.target, html: n.html.slice(0, 300), failure_summary: n.failureSummary }))
                        }))
                      };
                    }""",
                    AXE_RULES,
                )
                evidence["details"]["independent_oracle"] = {
                    "engine": "axe-core",
                    "rules": AXE_RULES,
                    "violation_count": len(oracle["violations"]),
                    "violations": oracle["violations"],
                }

                heuristic_disposition = _classify_heuristic_finding(
                    metrics["unnamed_control_details"],
                    len(oracle["violations"]),
                )
                evidence["details"]["heuristic_disposition"] = heuristic_disposition

                failures = []
                if not metrics["lang_present"]:
                    failures.append("document language is missing")
                if not metrics["title_present"]:
                    failures.append("document title is missing")
                if metrics["images_missing_alt"]:
                    failures.append(f"{metrics['images_missing_alt']} rendered image(s) lack an alt attribute")
                if oracle["violations"]:
                    failures.append(f"axe-core found {len(oracle['violations'])} selected accessibility rule violation(s)")
                if heuristic_disposition == "INCONCLUSIVE":
                    failures.append(
                        f"{metrics['unnamed_interactive_controls']} DOM-heuristic unnamed control(s) lack independent oracle confirmation"
                    )

                if failures:
                    raise AssertionError("; ".join(failures))
                evidence["status"] = "PASS"
            finally:
                browser.close()
    except Exception as exc:
        evidence["details"]["error"] = f"{type(exc).__name__}: {exc}"
        OUTPUT.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        raise

    OUTPUT.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()

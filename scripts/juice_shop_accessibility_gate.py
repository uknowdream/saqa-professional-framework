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
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.username or parsed.password or parsed.port is None:
        raise ValueError("accessibility target must be credential-free HTTP on 127.0.0.1 with a port")


def _load_axe_source() -> str:
    if not AXE_CORE_PATH.is_file():
        raise FileNotFoundError(f"axe-core oracle not found: {AXE_CORE_PATH}")
    return AXE_CORE_PATH.read_text(encoding="utf-8")


def _classify_heuristic_finding(
    unnamed_controls: list[dict[str, object]], oracle_violation_count: int
) -> str:
    if not unnamed_controls:
        return "NONE"
    return "CONFIRMED_ORACLE" if oracle_violation_count > 0 else "INCONCLUSIVE"


def _guard_request(route) -> None:
    parsed = urlparse(route.request.url)
    base = urlparse(BASE_URL)
    if route.request.method != "GET":
        route.abort()
        return
    if (
        parsed.scheme != base.scheme
        or parsed.hostname != base.hostname
        or parsed.port != base.port
        or parsed.username
        or parsed.password
    ):
        route.abort()
        raise RuntimeError(f"blocked accessibility request outside authorized target origin: {route.request.url!r}")
    route.continue_()


def main() -> int:
    _assert_loopback_http(BASE_URL)
    if BROWSER not in ALLOWED_BROWSERS:
        raise ValueError(f"unsupported browser: {BROWSER}")

    from playwright.sync_api import sync_playwright

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    evidence = {
        "schema": "saqa.juice-shop-accessibility.v7",
        "test_id": f"juice-shop.accessibility-readiness.{BROWSER}",
        "status": "FAIL",
        "target": BASE_URL,
        "browser": BROWSER,
        "http_methods": ["GET"],
        "redirects_followed": "guarded",
        "destructive_actions": False,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "details": {},
    }

    try:
        axe_source = _load_axe_source()
        with sync_playwright() as playwright:
            browser = None
            context = None
            try:
                browser = getattr(playwright, BROWSER).launch(headless=True)
                context = browser.new_context(viewport={"width": 1440, "height": 900})
                context.route("**/*", _guard_request)
                page = context.new_page()
                response = page.goto(BASE_URL + "/", wait_until="domcontentloaded", timeout=15000)
                _assert_loopback_http(page.url)
                page.locator("app-root").wait_for(state="attached", timeout=15000)
                page.wait_for_function("document.body && document.body.innerText.trim().length > 0", timeout=15000)
                metrics = page.evaluate("""() => {
                  const text = e => (e?.textContent || '').replace(/\\s+/g, ' ').trim();
                  const labelledBy = e => (e.getAttribute('aria-labelledby') || '').split(/\\s+/).filter(Boolean)
                    .map(id => document.getElementById(id)?.textContent || '').join(' ').trim();
                  const explicitLabel = e => e.id ? [...document.querySelectorAll(`label[for=\\"${CSS.escape(e.id)}\\"]`)].map(label => text(label)).join(' ') : '';
                  const name = e => (e.getAttribute('aria-label') || labelledBy(e) || explicitLabel(e)
                    || e.closest('label')?.textContent || e.getAttribute('title') || text(e) || '').trim();
                  const rendered = e => { if (e.hidden || e.getAttribute('aria-hidden') === 'true') return false;
                    const s = getComputedStyle(e), r = e.getBoundingClientRect(); return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0; };
                  const controls = [...document.querySelectorAll('button,a[href],input,select,textarea,[role=\\"button\\"],[role=\\"link\\"],[role=\\"checkbox\\"],[role=\\"radio\\"],[role=\\"switch\\"],[role=\\"combobox\\"],[role=\\"textbox\\"]')]
                    .filter(rendered).filter(e => !(e.tagName.toLowerCase() === 'input' && (e.getAttribute('type') || '').toLowerCase() === 'hidden'));
                  const unnamed = controls.filter(e => !name(e)).map(e => ({tag:e.tagName.toLowerCase(),id:e.id||'',role:e.getAttribute('role')||'',type:e.getAttribute('type')||'',tab_index:e.tabIndex,outerHTML:e.outerHTML.slice(0,300)}));
                  return {lang_present:!!(document.documentElement.getAttribute('lang')||'').trim(),title_present:!!document.title.trim(),images_missing_alt:[...document.images].filter(rendered).filter(e=>!e.hasAttribute('alt')).length,interactive_control_count:controls.length,unnamed_interactive_controls:unnamed.length,unnamed_control_details:unnamed};
                }""")
                evidence["details"] = {"status_code": response.status if response else None, **metrics}
                if not response or response.status < 200 or response.status >= 400:
                    raise AssertionError(f"expected successful page response, got {response.status if response else None}")
                page.add_script_tag(content=axe_source)
                oracle = page.evaluate("""async rules => {
                  const r = await axe.run(document, {runOnly: {type: 'rule', values: rules}});
                  return r.violations.map(v => ({id:v.id,impact:v.impact,help:v.help,nodes:v.nodes.map(n=>({target:n.target,html:n.html.slice(0,300),failure_summary:n.failureSummary}))}));
                }""", AXE_RULES)
                evidence["details"]["independent_oracle"] = {"engine":"axe-core","rules":AXE_RULES,"violation_count":len(oracle),"violations":oracle}
                disposition = _classify_heuristic_finding(metrics["unnamed_control_details"], len(oracle))
                evidence["details"]["heuristic_disposition"] = disposition
                failures = []
                if not metrics["lang_present"]: failures.append("document language is missing")
                if not metrics["title_present"]: failures.append("document title is missing")
                if metrics["images_missing_alt"]: failures.append(f"{metrics['images_missing_alt']} rendered image(s) lack alt")
                if oracle: failures.append(f"axe-core found {len(oracle)} selected rule violation(s)")
                if disposition == "INCONCLUSIVE": failures.append(f"{metrics['unnamed_interactive_controls']} user-operable DOM-heuristic unnamed control(s) require independent oracle correlation")
                if failures: raise AssertionError("; ".join(failures))
                context.close(); context = None
                browser.close(); browser = None
                evidence["status"] = "PASS"
            except Exception as exc:
                evidence["details"]["error"] = f"{type(exc).__name__}: {exc}"
            finally:
                if context is not None:
                    try: context.close()
                    except Exception: pass
                if browser is not None:
                    try: browser.close()
                    except Exception: pass
    except Exception as exc:
        evidence["details"]["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        OUTPUT.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

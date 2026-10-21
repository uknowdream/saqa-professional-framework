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
AXE_RULES = ["aria-input-field-name", "button-name", "link-name"]
AXE_DIAGNOSTIC_RULES = AXE_RULES + ["document-title", "html-has-lang", "image-alt", "heading-order", "landmark-one-main", "color-contrast"]
ORACLE_CONFIRMATION_STATUS = "CONFIRMED_ORACLE"


def _assert_loopback_http(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.username or parsed.password or parsed.port is None:
        raise ValueError("accessibility target must be credential-free HTTP on 127.0.0.1 with a port")


def _load_axe_source() -> str:
    if not AXE_CORE_PATH.is_file():
        raise FileNotFoundError(f"axe-core oracle not found: {AXE_CORE_PATH}")
    return AXE_CORE_PATH.read_text(encoding="utf-8")


def _classify_heuristic_finding(unnamed_controls: list[dict[str, object]]) -> str:
    """Classify only keyboard-operable unnamed controls as diagnostic findings.

    INCONCLUSIVE is diagnostic evidence only The independent axe oracle remains authoritative
    until deterministic DOM/node correlation is implemented.

    The heuristic intentionally does not claim correlation with axe nodes. DOM controls
    removed from keyboard navigation (tabindex < 0) are non-user-operable implementation
    details and are excluded; the independent axe oracle remains authoritative.
    """
    if not unnamed_controls:
        return "NONE"
    return "INCONCLUSIVE"


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


def _summarize_keyboard_sequence(sequence: list[dict[str, object]], steps: int) -> dict[str, object]:
    """Summarize keyboard focus observations; all findings are diagnostic only."""
    def identity(item):
        return (item.get("tag"), item.get("id"), item.get("role"), item.get("text"))

    identities = {identity(item) for item in sequence}
    target_ids = [identity(item) for item in sequence]
    repeated_consecutive_targets = sum(
        1 for previous, current in zip(target_ids, target_ids[1:])
        if previous == current
    )
    repeated_cycle_periods = []
    # Flag repeated A/B/A/B and longer repeated cycles, not just adjacent identical nodes.
    max_period = min(5, len(target_ids) // 2)
    for period in range(2, max_period + 1):
        for offset in range(0, len(target_ids) - (2 * period) + 1):
            first = target_ids[offset:offset + period]
            second = target_ids[offset + period:offset + (2 * period)]
            if first == second and len(set(first)) > 1:
                repeated_cycle_periods.append(period)
                break

    def legacy_indicator_heuristic(item):
        return (
            (item.get("outline_style") not in {None, "", "none"}
             and item.get("outline_width") not in {None, "", "0px"})
            or item.get("box_shadow") not in {None, "", "none"}
            or item.get("outline_offset") not in {None, "", "0px"}
        )

    indicator_steps = sum(
        1 for item in sequence
        if (
            bool(item.get("focus_indicator_visible"))
            if "focus_indicator_visible" in item
            else bool(legacy_indicator_heuristic(item))
        )
    )
    trap_suspected = (
        (len(identities) > 1 and repeated_consecutive_targets >= 2)
        or bool(repeated_cycle_periods)
    )
    return {
        "method": "keyboard Tab only",
        "requested_steps": steps,
        "focused_steps": len(sequence),
        "unique_focus_targets": len(identities),
        "focus_visible_steps": sum(1 for item in sequence if item.get("focus_visible")),
        "visible_indicator_style_steps": indicator_steps,
        "repeated_consecutive_targets": repeated_consecutive_targets,
        "repeated_focus_cycle_periods": sorted(set(repeated_cycle_periods)),
        "keyboard_trap_suspected": trap_suspected,
        "sequence": sequence,
        "scope_note": "diagnostic smoke only; computed CSS indicators and repeated focus targets are heuristics, not proof of WCAG conformance. Manual focus-order, keyboard-trap, and visible-indicator verification remains required",
    }

def _keyboard_focus_sequence(page, steps: int = 10) -> dict[str, object]:
    """Record keyboard-only Tab traversal without claiming full WCAG conformance."""
    sequence = []
    for _ in range(steps):
        page.keyboard.press("Tab")
        state = page.evaluate("""() => {
          const e = document.activeElement;
          if (!e) return null;
          const text = (e.innerText || e.textContent || "").replace(/\\s+/g, " ").trim().slice(0, 100);
          const snapshot = element => {
            const s = getComputedStyle(element);
            return {
              outline_style: s.outlineStyle,
              outline_width: s.outlineWidth,
              outline_color: s.outlineColor,
              outline_offset: s.outlineOffset,
              box_shadow: s.boxShadow,
              border_top_style: s.borderTopStyle,
              border_top_width: s.borderTopWidth,
              border_top_color: s.borderTopColor
            };
          };
          const focusStyle = snapshot(e);
          // Compare focused and resting styles; static non-default CSS is not by itself a focus indicator.
          e.blur();
          const restingStyle = snapshot(e);
          e.focus({preventScroll: true});
          const restoredStyle = snapshot(e);
          const visibleColor = value => {
            if (!value || value === "transparent") return false;
            const rgba = value.match(/^rgba\\((.*)\\)$/i);
            if (rgba) {
              const components = rgba[1].split(",");
              return components.length < 4 || Number(components[3]) > 0;
            }
            if (/\\/\\s*0(?:\\.0+)?%?\\s*\\)/i.test(value)) return false;
            return true;
          };
          const changed = property => focusStyle[property] !== restingStyle[property];
          const outlinePainted = focusStyle.outline_style !== "none"
            && focusStyle.outline_width !== "0px"
            && visibleColor(focusStyle.outline_color)
            && ["outline_style", "outline_width", "outline_color", "outline_offset"].some(changed);
          const boxShadowPainted = focusStyle.box_shadow !== "none"
            && focusStyle.box_shadow !== ""
            && visibleColor(focusStyle.box_shadow)
            && changed("box_shadow");
          const borderPainted = focusStyle.border_top_style !== "none"
            && focusStyle.border_top_width !== "0px"
            && visibleColor(focusStyle.border_top_color)
            && ["border_top_style", "border_top_width", "border_top_color"].some(changed);
          const rect = e.getBoundingClientRect();
          return {
            tag: e.tagName.toLowerCase(),
            id: e.id || "",
            role: e.getAttribute("role") || "",
            text,
            tab_index: e.tabIndex,
            focus_visible: e.matches(":focus-visible"),
            rendered: rect.width > 0 && rect.height > 0 && getComputedStyle(e).visibility !== "hidden" && getComputedStyle(e).display !== "none",
            ...restoredStyle,
            focus_indicator_visible: Boolean(outlinePainted || boxShadowPainted || borderPainted),
            focus_style_changed_from_resting: Boolean(
              ["outline_style", "outline_width", "outline_color", "outline_offset",
               "box_shadow", "border_top_style", "border_top_width", "border_top_color"].some(changed)
            )
          };
        }""")
        if state and state["tag"] not in {"body", "html"}:
            sequence.append(state)
    return _summarize_keyboard_sequence(sequence, steps)


def main() -> int:
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
        _assert_loopback_http(BASE_URL)
        if BROWSER not in ALLOWED_BROWSERS:
            raise ValueError(f"unsupported browser: {BROWSER}")
        from playwright.sync_api import sync_playwright
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
                    .filter(rendered)
                    .filter(e => !e.matches(':disabled'))
                    .filter(e => e.getAttribute('aria-disabled') !== 'true')
                    .filter(e => e.tabIndex >= 0)
                    .filter(e => !(e.tagName.toLowerCase() === 'input' && (e.getAttribute('type') || '').toLowerCase() === 'hidden'));
                  const unnamed = controls.filter(e => !name(e)).map(e => ({tag:e.tagName.toLowerCase(),id:e.id||'',role:e.getAttribute('role')||'',type:e.getAttribute('type')||'',tab_index:e.tabIndex,outerHTML:e.outerHTML.slice(0,300)}));
                  return {lang_present:!!(document.documentElement.getAttribute('lang')||'').trim(),title_present:!!document.title.trim(),images_missing_alt:[...document.images].filter(rendered).filter(e=>!e.hasAttribute('alt')).length,interactive_control_count:controls.length,unnamed_interactive_controls:unnamed.length,unnamed_control_details:unnamed};
                }""")
                evidence["details"] = {"status_code": response.status if response else None, **metrics}
                keyboard = _keyboard_focus_sequence(page)
                evidence["details"]["keyboard_navigation"] = keyboard
                if not response or response.status < 200 or response.status >= 400:
                    raise AssertionError(f"expected successful page response, got {response.status if response else None}")
                page.add_script_tag(content=axe_source)
                oracle = page.evaluate("""async rules => {
                  const r = await axe.run(document, {runOnly: {type: 'rule', values: rules}});
                  return r.violations.map(v => ({id:v.id,impact:v.impact,help:v.help,nodes:v.nodes.map(n=>({target:n.target,html:n.html.slice(0,300),failure_summary:n.failureSummary}))}));
                }""", AXE_RULES)
                diagnostic_oracle = page.evaluate("""async rules => { const r = await axe.run(document, {runOnly: {type: "rule", values: rules}}); return r.violations.map(v => ({id:v.id,impact:v.impact,help:v.help,nodes:v.nodes.map(n => ({target:n.target,html:n.html.slice(0,300),failure_summary:n.failureSummary}))})); }""", AXE_DIAGNOSTIC_RULES)
                evidence["details"]["independent_oracle"] = {"engine":"axe-core","gated_rules":AXE_RULES,"diagnostic_rules":AXE_DIAGNOSTIC_RULES,"violation_count":len(oracle),"violations":oracle,"diagnostic_violation_count":len(diagnostic_oracle),"diagnostic_violations":diagnostic_oracle,"status": ORACLE_CONFIRMATION_STATUS if oracle else "NO_ORACLE_VIOLATIONS"}
                # Repeat keyboard-only traversal after a fresh load at a narrow mobile viewport.
                # This remains diagnostic smoke evidence, not a claim of native mobile or WCAG certification.
                page.set_viewport_size({"width": 390, "height": 844})
                mobile_response = page.goto(BASE_URL + "/", wait_until="domcontentloaded", timeout=15000)
                _assert_loopback_http(page.url)
                page.locator("app-root").wait_for(state="attached", timeout=15000)
                page.wait_for_function("document.body && document.body.innerText.trim().length > 0", timeout=15000)
                mobile_keyboard = _keyboard_focus_sequence(page)
                evidence["details"]["keyboard_navigation_mobile_viewport"] = {
                    "viewport": {"width": 390, "height": 844},
                    "status_code": mobile_response.status if mobile_response else None,
                    **mobile_keyboard,
                }
                disposition = _classify_heuristic_finding(metrics["unnamed_control_details"])
                evidence["details"]["heuristic_disposition"] = disposition
                failures = []
                if keyboard["unique_focus_targets"] == 0: failures.append("keyboard Tab sequence did not reach a focusable target")
                if not mobile_response or mobile_response.status < 200 or mobile_response.status >= 400: failures.append("mobile viewport page reload did not return a successful response")
                if mobile_keyboard["unique_focus_targets"] == 0: failures.append("mobile viewport keyboard Tab sequence did not reach a focusable target")
                if not metrics["lang_present"]: failures.append("document language is missing")
                if not metrics["title_present"]: failures.append("document title is missing")
                if metrics["images_missing_alt"]: failures.append(f"{metrics['images_missing_alt']} rendered image(s) lack alt")
                if oracle: failures.append(f"axe-core found {len(oracle)} selected rule violation(s)")
                if disposition == "INCONCLUSIVE":
                    evidence["details"]["heuristic_note"] = "unnamed keyboard-operable control(s) detected; independent axe result is authoritative for the selected rules until deterministic node correlation is implemented"
                    evidence["details"]["heuristic_authority"] = "independent_axe"
                if disposition == "INCONCLUSIVE":
                    failures = [item for item in failures if item != "heuristic accessibility finding is inconclusive"]
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

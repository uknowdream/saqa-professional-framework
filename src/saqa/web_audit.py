"""Multi-Pillar Automated Deep Website & Mobile-Web QA Auditor.

Covers:
- Pillar 1: TLS/SSL Protocol & Certificate Expiry
- Pillar 2: OWASP Security Headers & Cookie Hygiene
- Pillar 3: WCAG 2.2 Semantic DOM Accessibility
- Pillar 4: SEO Metadata, JSON-LD & Discoverability
- Pillar 5: Parallel Broken Link, Static Asset & Mixed-Content Crawler
- Pillar 6: Read-Only Sensitive Dotfile Exposure Hygiene
- Pillar 7: Multi-Sample Keep-Alive Performance & Cache Profile
- Pillar 8 (Optional): Live Headless Browser SPA Rendered DOM, Core Web Vitals & Runtime
- Pillar 9 (Optional): Modern Web, API & Mobile App-Link Security (CORS, SRI, security.txt, Android/iOS Universal Links, GraphQL Introspection)
- Multi-Viewport Responsive Matrix (Optional): Desktop / Tablet / Mobile overflow & tap targets
- Multi-Page Site Crawler (Optional): Sitemap + BFS multi-page WCAG/SEO/HTTP crawler
"""
from __future__ import annotations

import json
import re
import socket
import ssl
from collections import deque
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urldefrag, urljoin, urlparse

from . import __version__
from .analytics import analyze_records, compute_latency_stats
from .api import ApiResponse
from .evidence import EvidenceRecord, utc_now, write_manifest
from .http_pool import create_pooled_requester
from .i18n import normalize_lang, translate_finding_or_reason
from .pdf_report import render_pdf_report
from .reporting import render_html_report, render_junit_xml, render_markdown_report, render_sarif_report
from .url_safety import redact_url
from .visual_evidence import export_csv_matrix, render_analytics_svg, render_scorecard_png

_OWASP_HEADERS = (
    "strict-transport-security",
    "content-security-policy",
    "x-content-type-options",
    "x-frame-options",
    "referrer-policy",
    "permissions-policy",
    "cross-origin-opener-policy",
    "cross-origin-resource-policy",
)

_SENSITIVE_PATTERNS = (
    re.compile(r"ref:\s*refs/heads/", re.IGNORECASE),
    re.compile(r"(DB_PASSWORD|AWS_SECRET_ACCESS_KEY|PRIVATE_KEY|API_SECRET)\s*=", re.IGNORECASE),
)

_SITEMAP_LOC_RE = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.IGNORECASE)


@dataclass(frozen=True)
class DeepAuditResult:
    """Complete output of an automated deep web & app QA audit."""

    target_url: str
    records: tuple[EvidenceRecord, ...]
    analytics: dict[str, Any]
    findings: tuple[dict[str, Any], ...]
    manifest_path: Path | None = None
    manifest_sha256: str | None = None
    summary_path: Path | None = None

    @property
    def passed(self) -> bool:
        return self.analytics["overall_status"] == "PASS"


class _DomAuditParser(HTMLParser):
    """Lightweight stdlib HTML parser collecting WCAG, SEO, JSON-LD, SRI, and link/asset signals."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.html_lang: str | None = None
        self.title_parts: list[str] = []
        self._in_title = False
        self._in_jsonld = False
        self._jsonld_buf: list[str] = []
        self.jsonld_blocks: list[str] = []
        self.meta_by_name: dict[str, str] = {}
        self.meta_by_prop: dict[str, str] = {}
        self.canonical_href: str | None = None
        self.headings: list[tuple[int, str]] = []
        self._current_heading_level: int | None = None
        self._heading_buf: list[str] = []
        self.has_main_landmark = False
        self.has_nav_or_header = False
        self.images_total = 0
        self.images_missing_alt: list[str] = []
        self.links: list[dict[str, Any]] = []
        self.assets: list[dict[str, str]] = []
        self.buttons: list[dict[str, Any]] = []
        self._active_link: dict[str, Any] | None = None
        self._active_button: dict[str, Any] | None = None
        self.label_for_ids: set[str] = set()
        self.form_inputs: list[dict[str, str]] = []
        self._in_label = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        attr_map = {k.lower(): (v if v is not None else "") for k, v in attrs}

        if t == "html":
            lang = attr_map.get("lang", "").strip()
            if lang:
                self.html_lang = lang
        elif t == "title":
            self._in_title = True
        elif t == "meta":
            name = attr_map.get("name", "").strip().lower()
            prop = attr_map.get("property", "").strip().lower()
            content = attr_map.get("content", "").strip()
            if name and content:
                self.meta_by_name[name] = content
            if prop and content:
                self.meta_by_prop[prop] = content
        elif t == "link":
            rel = attr_map.get("rel", "").lower()
            href = attr_map.get("href", "").strip()
            if "canonical" in rel.split() and href:
                self.canonical_href = href
            if href and any(r in rel for r in ("stylesheet", "icon", "manifest", "preload")):
                self.assets.append({
                    "tag": "link",
                    "rel": rel,
                    "url": href,
                    "integrity": attr_map.get("integrity", "").strip(),
                })
        elif t == "script":
            stype = attr_map.get("type", "").strip().lower()
            src = attr_map.get("src", "").strip()
            if stype == "application/ld+json":
                self._in_jsonld = True
                self._jsonld_buf = []
            elif src:
                self.assets.append({
                    "tag": "script",
                    "rel": "script",
                    "url": src,
                    "integrity": attr_map.get("integrity", "").strip(),
                })
        elif t in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._current_heading_level = int(t[1])
            self._heading_buf = []
        elif t == "main" or attr_map.get("role", "").lower() == "main":
            self.has_main_landmark = True
        elif t in {"nav", "header", "footer"}:
            self.has_nav_or_header = True
        elif t == "img":
            self.images_total += 1
            src = attr_map.get("src", "").strip()
            if src:
                self.assets.append({"tag": "img", "rel": "image", "url": src, "integrity": ""})
            if "alt" not in attr_map:
                self.images_missing_alt.append(src or "<inline-img>")
        elif t == "a":
            href = attr_map.get("href", "").strip()
            self._active_link = {
                "href": href,
                "aria_label": attr_map.get("aria-label", "").strip() or attr_map.get("title", "").strip(),
                "text": "",
                "has_img": False,
            }
        elif t == "button":
            self._active_button = {
                "aria_label": attr_map.get("aria-label", "").strip() or attr_map.get("title", "").strip(),
                "text": "",
            }
        elif t == "label":
            self._in_label = True
            for_id = attr_map.get("for", "").strip()
            if for_id:
                self.label_for_ids.add(for_id)
        elif t in {"input", "select", "textarea"}:
            input_type = attr_map.get("type", "text").strip().lower()
            if input_type not in {"hidden", "submit", "button", "reset"}:
                self.form_inputs.append({
                    "id": attr_map.get("id", "").strip(),
                    "name": attr_map.get("name", "").strip(),
                    "aria_label": attr_map.get("aria-label", "").strip() or attr_map.get("aria-labelledby", "").strip(),
                    "wrapped_in_label": "yes" if self._in_label else "no",
                })

        if self._active_link is not None and t in {"img", "svg"}:
            self._active_link["has_img"] = True

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t == "title":
            self._in_title = False
        elif t == "script" and self._in_jsonld:
            self._in_jsonld = False
            self.jsonld_blocks.append("".join(self._jsonld_buf).strip())
            self._jsonld_buf = []
        elif t in {"h1", "h2", "h3", "h4", "h5", "h6"} and self._current_heading_level is not None:
            self.headings.append((self._current_heading_level, "".join(self._heading_buf).strip()))
            self._current_heading_level = None
            self._heading_buf = []
        elif t == "a" and self._active_link is not None:
            self.links.append(self._active_link)
            self._active_link = None
        elif t == "button" and self._active_button is not None:
            self.buttons.append(self._active_button)
            self._active_button = None
        elif t == "label":
            self._in_label = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
        if self._in_jsonld:
            self._jsonld_buf.append(data)
        if self._current_heading_level is not None:
            self._heading_buf.append(data)
        if self._active_link is not None:
            self._active_link["text"] += data
        if self._active_button is not None:
            self._active_button["text"] += data


def inspect_tls_certificate(hostname: str, port: int = 443, *, timeout: float = 10.0) -> dict[str, Any]:
    """Perform a live read-only TLS handshake to verify certificate expiry and protocol strength."""
    ctx = ssl.create_default_context()
    with socket.create_connection((hostname, port), timeout=timeout) as sock:
        with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
            cert = ssock.getpeercert() or {}
            protocol = ssock.version() or "unknown"
            cipher_info = ssock.cipher()
            cipher_name = cipher_info[0] if cipher_info else "unknown"

    not_after_raw = str(cert.get("notAfter", ""))
    days_remaining: int | None = None
    expires_iso: str | None = None
    if not_after_raw:
        expires_dt = datetime.strptime(not_after_raw, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
        expires_iso = expires_dt.isoformat()
        days_remaining = int((expires_dt - datetime.now(timezone.utc)).total_seconds() // 86400)

    raw_issuer: Any = cert.get("issuer", ())
    raw_subject: Any = cert.get("subject", ())
    raw_sans: Any = cert.get("subjectAltName", ())
    issuer_parts = [f"{k}={v}" for rdn in raw_issuer for k, v in rdn]
    subject_parts = [f"{k}={v}" for rdn in raw_subject for k, v in rdn]
    sans = [val for kind, val in raw_sans if kind == "DNS"]

    return {
        "hostname": hostname,
        "port": port,
        "protocol": protocol,
        "cipher": cipher_name,
        "issuer": ", ".join(issuer_parts),
        "subject": ", ".join(subject_parts),
        "san_count": len(sans),
        "expires_at": expires_iso,
        "days_remaining": days_remaining,
    }


def _audit_dom_accessibility(dom: _DomAuditParser) -> tuple[str, list[str], list[str], dict[str, Any]]:
    checks_passed: list[str] = []
    failures: list[str] = []
    warnings: list[str] = []

    title = "".join(dom.title_parts).strip()
    if dom.html_lang:
        checks_passed.append(f"html_lang:{dom.html_lang}")
    else:
        failures.append("Missing lang attribute on <html> element (WCAG 3.1.1)")

    if title:
        checks_passed.append("title_present")
    else:
        failures.append("Missing or empty <title> element (WCAG 2.4.2)")

    h1_count = sum(1 for lvl, _ in dom.headings if lvl == 1)
    if h1_count == 1:
        checks_passed.append("single_h1")
    elif h1_count == 0:
        warnings.append("No <h1> landmark heading found in initial server HTML (may be client-rendered)")
    else:
        warnings.append(f"Multiple <h1> elements detected ({h1_count})")

    skipped_levels = []
    for (prev_lvl, _), (curr_lvl, _) in zip(dom.headings, dom.headings[1:], strict=False):
        if curr_lvl - prev_lvl > 1:
            skipped_levels.append(f"h{prev_lvl}->h{curr_lvl}")
    if skipped_levels:
        warnings.append(f"Skipped heading hierarchy levels: {', '.join(skipped_levels)}")
    else:
        checks_passed.append("heading_hierarchy_order")

    if dom.images_missing_alt:
        failures.append(f"{len(dom.images_missing_alt)} <img> element(s) missing alt attribute (WCAG 1.1.1)")
    else:
        checks_passed.append(f"images_alt_ok({dom.images_total})")

    unnamed_buttons = [
        b for b in dom.buttons if not (b["text"].strip() or b["aria_label"])
    ]
    if unnamed_buttons:
        failures.append(f"{len(unnamed_buttons)} <button> control(s) missing accessible name (WCAG 4.1.2)")
    else:
        checks_passed.append("buttons_named")

    unnamed_links = [
        lnk
        for lnk in dom.links
        if lnk["href"] and not (lnk["text"].strip() or lnk["aria_label"] or lnk["has_img"])
    ]
    if unnamed_links:
        warnings.append(f"{len(unnamed_links)} link(s) without visible text or aria-label")
    else:
        checks_passed.append("links_named")

    viewport = dom.meta_by_name.get("viewport", "").lower()
    if "user-scalable=no" in viewport or "maximum-scale=1" in viewport:
        failures.append("Viewport meta disables pinch-to-zoom (WCAG 1.4.4)")
    elif viewport:
        checks_passed.append("viewport_zoom_allowed")

    unlabeled_inputs = [
        inp
        for inp in dom.form_inputs
        if not (inp["aria_label"] or inp["wrapped_in_label"] == "yes" or (inp["id"] and inp["id"] in dom.label_for_ids))
    ]
    if unlabeled_inputs:
        failures.append(f"{len(unlabeled_inputs)} form input(s) missing <label> or aria-label (WCAG 1.3.1)")
    else:
        checks_passed.append("form_inputs_labeled")

    if dom.has_main_landmark:
        checks_passed.append("main_landmark_present")
    else:
        warnings.append("No <main> landmark found in initial HTML")

    status = "FAIL" if failures else "PASS"
    metrics = {
        "html_lang": dom.html_lang,
        "title": title,
        "h1_count": h1_count,
        "images_total": dom.images_total,
        "images_missing_alt": len(dom.images_missing_alt),
        "unnamed_buttons": len(unnamed_buttons),
        "unnamed_links": len(unnamed_links),
        "unlabeled_inputs": len(unlabeled_inputs),
        "has_main_landmark": dom.has_main_landmark,
        "warnings": warnings,
    }
    return status, checks_passed, failures, metrics


def _audit_security_headers(response: ApiResponse) -> tuple[str, list[str], list[str], dict[str, Any]]:
    checks_passed: list[str] = []
    failures: list[str] = []
    warnings: list[str] = []

    present = []
    missing = []
    for hdr in _OWASP_HEADERS:
        val = response.header(hdr)
        if val:
            present.append(hdr)
            checks_passed.append(f"header:{hdr}")
        else:
            missing.append(hdr)

    critical_missing = [h for h in ("strict-transport-security", "x-content-type-options") if h in missing]
    if critical_missing:
        warnings.append(f"Recommended baseline headers absent: {', '.join(critical_missing)}")

    xcto = (response.header("x-content-type-options") or "").strip().lower()
    if xcto and xcto != "nosniff":
        failures.append(f"X-Content-Type-Options should be 'nosniff', got {xcto!r}")

    csp = response.header("content-security-policy") or ""
    csp_ro = response.header("content-security-policy-report-only") or ""
    if csp and csp_ro:
        warnings.append("Both Content-Security-Policy and Content-Security-Policy-Report-Only are sent simultaneously")

    powered_by = response.header("x-powered-by")
    if powered_by:
        warnings.append(f"X-Powered-By discloses server technology: {powered_by}")
    else:
        checks_passed.append("no_x_powered_by_leak")

    insecure_cookies: list[str] = []
    for k, v in response.headers.items():
        if k.lower() == "set-cookie":
            low = v.lower()
            cookie_name = v.split("=", 1)[0].strip()
            if "secure" not in low or "httponly" not in low:
                insecure_cookies.append(cookie_name)
    if insecure_cookies:
        warnings.append(f"Cookie(s) missing Secure/HttpOnly flag: {', '.join(insecure_cookies)}")
    else:
        checks_passed.append("cookie_hygiene_ok")

    score = round((len(present) / len(_OWASP_HEADERS)) * 100.0, 1)
    status = "FAIL" if failures else "PASS"
    details = {
        "security_header_score_pct": score,
        "headers_present": present,
        "headers_missing": missing,
        "warnings": warnings,
    }
    return status, checks_passed, failures, details


def _audit_modern_security_and_applinks(
    target_url: str,
    base_url: str,
    origin_host: str,
    dom: _DomAuditParser,
    requester: Callable[..., ApiResponse],
    default_headers: Mapping[str, str],
    timeout: float,
) -> tuple[EvidenceRecord, list[dict[str, Any]]]:
    """Pillar 9: CORS reflection, SRI on third-party scripts, RFC 9116 security.txt, Mobile Universal/App Links, & GraphQL introspection."""
    checks_passed: list[str] = []
    failures: list[str] = []
    warnings: list[str] = []
    findings: list[dict[str, Any]] = []

    # 1. CORS Misconfiguration Probe (read-only GET with canary Origin)
    probe_origin = "https://saqa-cors-probe.invalid"
    cors_headers = {**default_headers, "Origin": probe_origin}
    cors_resp = requester(target_url, method="GET", headers=cors_headers, timeout=timeout, follow_redirects=True, use_environment_proxies=False)
    acao = (cors_resp.header("access-control-allow-origin") or "").strip()
    acac = (cors_resp.header("access-control-allow-credentials") or "").strip().lower()
    if acao == probe_origin:
        if acac == "true":
            failures.append("CRITICAL CORS: Server reflects arbitrary Origin with Access-Control-Allow-Credentials: true")
        else:
            warnings.append("CORS reflects arbitrary Origin header without strict allowlist")
    elif acao == "*" and acac == "true":
        failures.append("Invalid/insecure CORS: Access-Control-Allow-Origin '*' combined with Allow-Credentials 'true'")
    else:
        checks_passed.append("cors_origin_policy_safe")

    # 2. Subresource Integrity (SRI) on cross-origin third-party scripts
    missing_sri: list[str] = []
    root_domain = origin_host.removeprefix("www.")
    for asset in dom.assets:
        if asset["tag"] != "script":
            continue
        full_u = urljoin(target_url, asset["url"])
        up = urlparse(full_u)
        if up.hostname and up.hostname.lower() != origin_host and not up.hostname.lower().endswith("." + root_domain):
            if not asset.get("integrity", "").startswith(("sha256-", "sha384-", "sha512-")):
                missing_sri.append(redact_url(full_u))
    if missing_sri:
        warnings.append(f"{len(missing_sri)} external third-party <script> tag(s) missing Subresource Integrity (SRI)")
    else:
        checks_passed.append("third_party_sri_ok")

    # 3. RFC 9116 /.well-known/security.txt & Mobile App Deep-Links (Android assetlinks.json + iOS apple-app-site-association)
    sec_txt = requester(f"{base_url}/.well-known/security.txt", method="GET", headers=default_headers, timeout=timeout, follow_redirects=True, use_environment_proxies=False)
    if sec_txt.status_code == 200 and "contact:" in sec_txt.text.lower():
        checks_passed.append("rfc9116_security_txt_present")

    for mobile_well_known in ("/.well-known/assetlinks.json", "/.well-known/apple-app-site-association"):
        mw_resp = requester(f"{base_url}{mobile_well_known}", method="GET", headers=default_headers, timeout=timeout, follow_redirects=True, use_environment_proxies=False)
        ctype = (mw_resp.header("content-type") or "").lower()
        if mw_resp.status_code == 200 and "json" in ctype:
            try:
                mw_resp.json()
                checks_passed.append(f"mobile_applink_valid:{mobile_well_known}")
            except Exception:
                failures.append(f"Mobile deep-link file {mobile_well_known} returned HTTP 200 with malformed JSON")

    # 4. Read-only GraphQL Introspection Leak Probe
    gql_resp = requester(
        f"{base_url}/graphql?query=%7B__schema%7BqueryType%7Bname%7D%7D%7D",
        method="GET",
        headers={**default_headers, "Accept": "application/json"},
        timeout=timeout,
        follow_redirects=False,
        use_environment_proxies=False,
    )
    if gql_resp.status_code == 200 and '"__schema"' in gql_resp.text:
        warnings.append("GraphQL Introspection is publicly enabled on /graphql — disable in production unless public API")
    else:
        checks_passed.append("graphql_introspection_protected")

    for w in warnings:
        findings.append({"severity": "MEDIUM", "pillar": "Modern Web & App Security", "message": w})

    rec = EvidenceRecord(
        test_id="pillar-9.modern-web-and-app-security",
        status="FAIL" if failures else "PASS",
        observed_at=utc_now(),
        target=redact_url(target_url),
        details={
            "suite": f"deep-audit-{origin_host}",
            "case_name": "Pillar 9 — CORS, SRI, RFC 9116, Mobile App-Links & GraphQL Security Audit",
            "tags": ["security", "cors", "sri", "api", "graphql", "mobile"],
            "http_method": "GET",
            "status_code": cors_resp.status_code or 200,
            "elapsed_ms": round(cors_resp.elapsed_ms, 3),
            "checks_passed": checks_passed,
            "failure_reasons": failures,
            "warnings": warnings,
            "missing_sri_scripts": missing_sri[:10],
        },
    )
    return rec, findings


def _run_multipage_crawl(
    start_url: str,
    base_url: str,
    origin_host: str,
    initial_dom: _DomAuditParser,
    sitemap_xml: str,
    *,
    extra_seed_links: list[str] | None = None,
    max_pages: int,
    requester: Callable[..., ApiResponse],
    default_headers: Mapping[str, str],
    timeout: float,
) -> tuple[EvidenceRecord, list[dict[str, Any]]]:
    """BFS + Sitemap + SPA-DOM multi-page deep QA crawler auditing WCAG DOM, SEO, and HTTP health across subpages."""
    visited: set[str] = {urldefrag(start_url)[0].rstrip("/") or start_url}
    queue: deque[str] = deque()

    # Seed from sitemap.xml <loc> entries first, then landing page & SPA-rendered internal links
    for loc in _SITEMAP_LOC_RE.findall(sitemap_xml):
        clean_u = urldefrag(loc.strip())[0]
        up = urlparse(clean_u)
        if up.scheme in {"http", "https"} and up.hostname and up.hostname.lower() == origin_host:
            key = clean_u.rstrip("/") or clean_u
            if key not in visited:
                queue.append(clean_u)

    raw_hrefs = [lnk["href"] for lnk in initial_dom.links] + list(extra_seed_links or [])
    for href in raw_hrefs:
        if not href or href.startswith(("data:", "javascript:", "mailto:", "tel:", "#")):
            continue
        clean_u = urldefrag(urljoin(start_url, href))[0]
        up = urlparse(clean_u)
        if up.scheme in {"http", "https"} and up.hostname and up.hostname.lower() == origin_host:
            if not any(up.path.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".svg", ".webp", ".css", ".js", ".pdf", ".zip", ".ico", ".xml")):
                key = clean_u.rstrip("/") or clean_u
                if key not in visited and clean_u not in queue:
                    queue.append(clean_u)

    crawled_pages: list[dict[str, Any]] = []
    failures: list[str] = []
    findings: list[dict[str, Any]] = []
    latencies: list[float] = []

    while queue and len(crawled_pages) < max(1, max_pages - 1):
        page_url = queue.popleft()
        norm_key = page_url.rstrip("/") or page_url
        if norm_key in visited:
            continue
        visited.add(norm_key)

        safe_page_ref = f"{redact_url(page_url)}{urlparse(page_url).path}"
        resp = requester(page_url, method="GET", headers=default_headers, timeout=timeout, follow_redirects=True, use_environment_proxies=False)
        latencies.append(round(resp.elapsed_ms, 2))
        ctype = (resp.header("content-type") or "").lower()
        if resp.status_code == 0 or resp.status_code >= 400:
            failures.append(f"Subpage {safe_page_ref} returned HTTP {resp.status_code}")
            crawled_pages.append({"url": safe_page_ref, "status_code": resp.status_code, "a11y_status": "FAIL"})
            continue

        if "html" not in ctype and "<html" not in resp.text[:500].lower():
            continue

        sub_dom = _DomAuditParser()
        sub_dom.feed(resp.text)
        a11y_st, _, a11y_fail, _ = _audit_dom_accessibility(sub_dom)
        if a11y_fail:
            failures.append(f"Subpage {safe_page_ref} WCAG failure: {a11y_fail[0]}")
        if not sub_dom.meta_by_name.get("description"):
            findings.append({"severity": "LOW", "pillar": "Multi-Page SEO", "message": f"Subpage {safe_page_ref} missing meta description"})

        crawled_pages.append({
            "url": safe_page_ref,
            "status_code": resp.status_code,
            "elapsed_ms": round(resp.elapsed_ms, 2),
            "a11y_status": a11y_st,
            "title": "".join(sub_dom.title_parts).strip()[:80],
        })

        # Discover deeper links (BFS)
        for lnk in sub_dom.links:
            href = lnk["href"]
            if not href or href.startswith(("data:", "javascript:", "mailto:", "tel:", "#")):
                continue
            next_u = urldefrag(urljoin(page_url, href))[0]
            nup = urlparse(next_u)
            if nup.scheme in {"http", "https"} and nup.hostname and nup.hostname.lower() == origin_host:
                nkey = next_u.rstrip("/") or next_u
                if nkey not in visited and next_u not in queue:
                    queue.append(next_u)

    checks = [f"subpages_audited:{len(crawled_pages)}", f"total_pages_covered:{1 + len(crawled_pages)}"]
    if not failures:
        checks.append("all_crawled_subpages_healthy")

    rec = EvidenceRecord(
        test_id="multi-page.site-crawl-audit",
        status="FAIL" if failures else "PASS",
        observed_at=utc_now(),
        target=redact_url(start_url),
        details={
            "suite": f"deep-audit-{origin_host}",
            "case_name": f"Multi-Page Sitemap & BFS Deep Site Crawler ({1 + len(crawled_pages)} page(s))",
            "tags": ["web", "crawl", "a11y", "seo"],
            "http_method": "GET",
            "status_code": 200 if not failures else 500,
            "elapsed_ms": round(sum(latencies) / len(latencies), 3) if latencies else 0.0,
            "checks_passed": checks,
            "failure_reasons": failures,
            "pages": crawled_pages,
        },
    )
    return rec, findings


def run_deep_web_audit(
    target_url: str,
    *,
    output_dir: Path | None = None,
    max_links: int = 18,
    perf_samples: int = 3,
    timeout: float = 15.0,
    include_spa_audit: bool = False,
    include_modern_security: bool = False,
    include_responsive_audit: bool = False,
    crawl_max_pages: int = 1,
    extra_headers: Mapping[str, str] | None = None,
    cookies: str | Mapping[str, str] | None = None,
    lang: str = "en",
    requester: Callable[..., ApiResponse] | None = None,
    tls_inspector: Callable[..., dict[str, Any]] = inspect_tls_certificate,
) -> DeepAuditResult:
    """Execute a comprehensive multi-pillar read-only QA audit against an authorized HTTP(S) website or web-app."""
    parsed = urlparse(target_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"target_url must be a valid http/https URL: {target_url!r}")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("target_url must not contain embedded credentials")

    pool_ctx = create_pooled_requester(max_connections=12) if requester is None else nullcontext(requester)
    with pool_ctx as active_req:
        return _run_deep_web_audit_impl(
            target_url,
            parsed=parsed,
            output_dir=output_dir,
            max_links=max_links,
            perf_samples=perf_samples,
            timeout=timeout,
            include_spa_audit=include_spa_audit,
            include_modern_security=include_modern_security,
            include_responsive_audit=include_responsive_audit,
            crawl_max_pages=crawl_max_pages,
            extra_headers=extra_headers,
            cookies=cookies,
            lang=lang,
            requester=active_req,
            tls_inspector=tls_inspector,
        )


def _run_deep_web_audit_impl(
    target_url: str,
    *,
    parsed,
    output_dir: Path | None,
    max_links: int,
    perf_samples: int,
    timeout: float,
    include_spa_audit: bool,
    include_modern_security: bool,
    include_responsive_audit: bool,
    crawl_max_pages: int,
    extra_headers: Mapping[str, str] | None,
    cookies: str | Mapping[str, str] | None,
    lang: str,
    requester: Callable[..., ApiResponse],
    tls_inspector: Callable[..., dict[str, Any]],
) -> DeepAuditResult:
    code = normalize_lang(lang)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    redacted_target = redact_url(target_url)
    suite_name = f"deep-audit-{parsed.hostname}"
    default_headers: dict[str, str] = {
        "User-Agent": f"SAQA-Professional-Framework/{__version__}",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "identity",
    }
    if extra_headers:
        default_headers.update(extra_headers)
    if cookies:
        if isinstance(cookies, Mapping):
            default_headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
        else:
            default_headers["Cookie"] = str(cookies)

    records: list[EvidenceRecord] = []
    findings: list[dict[str, Any]] = []

    landing = requester(
        target_url,
        method="GET",
        headers=default_headers,
        timeout=timeout,
        follow_redirects=True,
        use_environment_proxies=False,
    )
    if (landing.status_code == 0 and landing.error) or landing.status_code >= 400:
        status_val = "BLOCKED" if landing.status_code in {0, 403, 429} else "FAIL"
        reason = landing.error or f"Landing page returned HTTP {landing.status_code}"
        blocked_rec = EvidenceRecord(
            test_id="deep-audit.landing-reachability",
            status=status_val,
            observed_at=utc_now(),
            target=redacted_target,
            details={
                "suite": suite_name,
                "case_name": "Landing page reachability",
                "tags": ["web", "smoke"],
                "http_method": "GET",
                "status_code": landing.status_code,
                "elapsed_ms": round(landing.elapsed_ms, 3),
                "failure_reasons": [reason],
            },
        )
        records.append(blocked_rec)
        analytics = analyze_records(records)
        return DeepAuditResult(target_url, tuple(records), analytics, tuple(findings))

    dom = _DomAuditParser()
    dom.feed(landing.text)

    # ── PILLAR 1: TLS / SSL Certificate & Protocol Audit ──────────────────────
    if parsed.scheme == "https":
        tls_port = parsed.port or 443
        try:
            tls_info = tls_inspector(parsed.hostname, tls_port, timeout=timeout)
            days = tls_info.get("days_remaining")
            tls_failures: list[str] = []
            tls_checks = [f"protocol:{tls_info['protocol']}", f"cipher:{tls_info['cipher']}"]
            if days is not None and days < 7:
                tls_failures.append(f"TLS certificate expires in {days} day(s) (< 7 day threshold)")
            elif days is not None:
                tls_checks.append(f"cert_valid_days:{days}")
                if days < 30:
                    findings.append({"severity": "MEDIUM", "pillar": "TLS", "message": f"TLS certificate expires in {days} days — schedule renewal"})
            tls_status = "FAIL" if tls_failures else "PASS"
            records.append(
                EvidenceRecord(
                    test_id="pillar-1.tls-certificate-audit",
                    status=tls_status,
                    observed_at=utc_now(),
                    target=redacted_target,
                    details={
                        "suite": suite_name,
                        "case_name": "Pillar 1 — TLS/SSL Protocol & Certificate Expiry Audit",
                        "tags": ["security", "tls"],
                        "http_method": "GET",
                        "status_code": landing.status_code,
                        "elapsed_ms": round(landing.elapsed_ms, 3),
                        "checks_passed": tls_checks,
                        "failure_reasons": tls_failures,
                        **tls_info,
                    },
                )
            )
        except Exception as exc:
            records.append(
                EvidenceRecord(
                    test_id="pillar-1.tls-certificate-audit",
                    status="FAIL",
                    observed_at=utc_now(),
                    target=redacted_target,
                    details={
                        "suite": suite_name,
                        "case_name": "Pillar 1 — TLS/SSL Protocol & Certificate Expiry Audit",
                        "tags": ["security", "tls"],
                        "http_method": "GET",
                        "status_code": 0,
                        "elapsed_ms": 0.0,
                        "failure_reasons": [f"TLS handshake error: {exc}"],
                    },
                )
            )
    else:
        records.append(
            EvidenceRecord(
                test_id="pillar-1.tls-certificate-audit",
                status="NOT_APPLICABLE",
                observed_at=utc_now(),
                target=redacted_target,
                details={
                    "suite": suite_name,
                    "case_name": "Pillar 1 — TLS/SSL Audit (HTTP target)",
                    "tags": ["security", "tls"],
                    "http_method": "GET",
                    "status_code": landing.status_code,
                    "elapsed_ms": round(landing.elapsed_ms, 3),
                },
            )
        )

    # ── PILLAR 2: HTTP Security Headers & Cookie Hygiene Audit ────────────────
    sec_status, sec_checks, sec_failures, sec_metrics = _audit_security_headers(landing)
    for w in sec_metrics["warnings"]:
        findings.append({"severity": "LOW", "pillar": "Security Headers", "message": w})
    records.append(
        EvidenceRecord(
            test_id="pillar-2.security-headers-and-cookies",
            status=sec_status,
            observed_at=utc_now(),
            target=redacted_target,
            details={
                "suite": suite_name,
                "case_name": "Pillar 2 — OWASP Security Headers & Cookie Hygiene Audit",
                "tags": ["security", "headers"],
                "http_method": "GET",
                "status_code": landing.status_code,
                "elapsed_ms": round(landing.elapsed_ms, 3),
                "checks_passed": sec_checks,
                "failure_reasons": sec_failures,
                **sec_metrics,
            },
        )
    )

    # ── PILLAR 3: Deep WCAG 2.2 Static DOM Accessibility Audit ────────────────
    a11y_status, a11y_checks, a11y_failures, a11y_metrics = _audit_dom_accessibility(dom)
    for w in a11y_metrics["warnings"]:
        findings.append({"severity": "MEDIUM", "pillar": "Accessibility", "message": w})
    records.append(
        EvidenceRecord(
            test_id="pillar-3.dom-wcag-accessibility",
            status=a11y_status,
            observed_at=utc_now(),
            target=redacted_target,
            details={
                "suite": suite_name,
                "case_name": "Pillar 3 — WCAG 2.2 Semantic DOM Accessibility Audit",
                "tags": ["a11y", "accessibility", "web"],
                "http_method": "GET",
                "status_code": landing.status_code,
                "elapsed_ms": round(landing.elapsed_ms, 3),
                "checks_passed": a11y_checks,
                "failure_reasons": a11y_failures,
                **a11y_metrics,
            },
        )
    )

    # ── PILLAR 4: SEO, JSON-LD Structured Data & Discoverability Audit ────────
    seo_checks: list[str] = []
    seo_failures: list[str] = []
    seo_warnings: list[str] = []
    if dom.meta_by_name.get("description"):
        seo_checks.append("meta_description")
    else:
        seo_warnings.append("Missing <meta name='description'>")
    if dom.canonical_href:
        seo_checks.append("canonical_link")
    else:
        seo_warnings.append("Missing <link rel='canonical'>")
    if dom.meta_by_prop.get("og:title") and dom.meta_by_prop.get("og:description"):
        seo_checks.append("opengraph_tags")
    else:
        seo_warnings.append("Incomplete OpenGraph metadata (og:title / og:description)")

    valid_jsonld = 0
    for idx, raw_block in enumerate(dom.jsonld_blocks, start=1):
        try:
            parsed_ld = json.loads(raw_block)
            if isinstance(parsed_ld, (dict, list)):
                valid_jsonld += 1
            else:
                seo_failures.append(f"JSON-LD block #{idx} is not an object or array")
        except json.JSONDecodeError as exc:
            seo_failures.append(f"Invalid JSON-LD block #{idx}: {exc.msg}")
    if valid_jsonld:
        seo_checks.append(f"valid_jsonld_blocks:{valid_jsonld}")

    discoverability: dict[str, int] = {}
    sitemap_body = ""
    for meta_path in ("/robots.txt", "/sitemap.xml", "/manifest.webmanifest"):
        resp = requester(f"{base_url}{meta_path}", method="GET", headers=default_headers, timeout=timeout, follow_redirects=True, use_environment_proxies=False)
        discoverability[meta_path] = resp.status_code
        if resp.status_code == 200:
            seo_checks.append(f"endpoint:{meta_path}")
            if meta_path == "/sitemap.xml":
                sitemap_body = resp.text
            elif meta_path == "/manifest.webmanifest":
                try:
                    resp.json()
                    seo_checks.append("manifest_valid_json")
                except Exception:
                    seo_failures.append("/manifest.webmanifest returned HTTP 200 but invalid JSON")

    for w in seo_warnings:
        findings.append({"severity": "LOW", "pillar": "SEO", "message": w})
    records.append(
        EvidenceRecord(
            test_id="pillar-4.seo-and-structured-data",
            status="FAIL" if seo_failures else "PASS",
            observed_at=utc_now(),
            target=redacted_target,
            details={
                "suite": suite_name,
                "case_name": "Pillar 4 — SEO Metadata, JSON-LD & Discoverability Audit",
                "tags": ["seo", "api", "contract"],
                "http_method": "GET",
                "status_code": landing.status_code,
                "elapsed_ms": round(landing.elapsed_ms, 3),
                "checks_passed": seo_checks,
                "failure_reasons": seo_failures,
                "jsonld_blocks_valid": valid_jsonld,
                "discoverability": discoverability,
                "warnings": seo_warnings,
            },
        )
    )

    # ── PILLAR 5: Automated Broken Link, Static Asset & Mixed-Content Crawler ─
    candidate_urls: list[str] = []
    seen_urls: set[str] = set()
    mixed_content: list[str] = []
    origin_host = parsed.hostname.lower()

    for asset in dom.assets:
        raw_u = asset["url"]
        if raw_u.startswith(("data:", "javascript:", "mailto:", "#")):
            continue
        full_u = urljoin(target_url, raw_u)
        up = urlparse(full_u)
        if parsed.scheme == "https" and up.scheme == "http":
            mixed_content.append(redact_url(full_u))
        if up.scheme in {"http", "https"} and up.hostname and (
            up.hostname.lower() == origin_host or up.hostname.lower().endswith("." + origin_host.removeprefix("www."))
        ):
            if full_u not in seen_urls:
                seen_urls.add(full_u)
                candidate_urls.append(full_u)

    for lnk in dom.links:
        href = lnk["href"]
        if not href or href.startswith(("data:", "javascript:", "mailto:", "tel:", "#")):
            continue
        full_u = urljoin(target_url, href)
        up = urlparse(full_u)
        if up.scheme in {"http", "https"} and up.hostname and up.hostname.lower() == origin_host:
            if full_u not in seen_urls:
                seen_urls.add(full_u)
                candidate_urls.append(full_u)

    checked_urls = candidate_urls[: max(1, max_links)]
    broken_links: list[dict[str, Any]] = []
    asset_latencies: list[float] = []
    if checked_urls:
        def _probe_link(u: str) -> tuple[str, ApiResponse]:
            return u, requester(u, method="GET", headers=default_headers, timeout=timeout, follow_redirects=True, use_environment_proxies=False)

        with ThreadPoolExecutor(max_workers=min(6, len(checked_urls))) as pool:
            for u, resp in pool.map(_probe_link, checked_urls):
                asset_latencies.append(round(resp.elapsed_ms, 2))
                if resp.status_code == 0 or resp.status_code >= 400:
                    broken_links.append({"url": u, "status_code": resp.status_code, "error": resp.error})

    link_failures: list[str] = []
    link_checks: list[str] = [f"checked_urls:{len(checked_urls)}"]
    if mixed_content:
        link_failures.append(f"Mixed-content HTTP asset(s) detected on HTTPS page: {len(mixed_content)}")
    else:
        link_checks.append("no_mixed_content")
    if broken_links:
        link_failures.append(
            f"{len(broken_links)} broken link/asset(s) found: "
            + ", ".join(f"{b['url']} ({b['status_code']})" for b in broken_links[:5])
        )
    else:
        link_checks.append("zero_broken_links_and_assets")

    records.append(
        EvidenceRecord(
            test_id="pillar-5.broken-links-and-assets",
            status="FAIL" if link_failures else "PASS",
            observed_at=utc_now(),
            target=redacted_target,
            details={
                "suite": suite_name,
                "case_name": "Pillar 5 — Automated Broken Link, Static Asset & Mixed-Content Crawler",
                "tags": ["web", "assets", "pwa", "css", "js"],
                "http_method": "GET",
                "status_code": 200 if not broken_links else broken_links[0]["status_code"],
                "elapsed_ms": round(sum(asset_latencies) / len(asset_latencies), 3) if asset_latencies else 0.0,
                "checks_passed": link_checks,
                "failure_reasons": link_failures,
                "urls_checked": len(checked_urls),
                "broken_links": broken_links,
                "mixed_content": mixed_content,
            },
        )
    )

    # ── PILLAR 6: Non-Destructive Sensitive Exposure Hygiene Probe ────────────
    exposure_failures: list[str] = []
    exposure_checks: list[str] = []
    for probe_path in ("/.env", "/.git/HEAD"):
        probe_resp = requester(f"{base_url}{probe_path}", method="GET", headers=default_headers, timeout=timeout, follow_redirects=False, use_environment_proxies=False)
        leaked = probe_resp.status_code == 200 and any(pat.search(probe_resp.text) for pat in _SENSITIVE_PATTERNS)
        if leaked:
            exposure_failures.append(f"CRITICAL: Sensitive file exposed at {probe_path} (HTTP 200)")
        else:
            exposure_checks.append(f"protected:{probe_path}(HTTP {probe_resp.status_code})")

    records.append(
        EvidenceRecord(
            test_id="pillar-6.sensitive-exposure-hygiene",
            status="FAIL" if exposure_failures else "PASS",
            observed_at=utc_now(),
            target=redacted_target,
            details={
                "suite": suite_name,
                "case_name": "Pillar 6 — Read-Only Sensitive Dotfile Exposure Hygiene Audit",
                "tags": ["security"],
                "http_method": "GET",
                "status_code": 200 if exposure_failures else 404,
                "elapsed_ms": round(landing.elapsed_ms, 3),
                "checks_passed": exposure_checks,
                "failure_reasons": exposure_failures,
            },
        )
    )

    # ── PILLAR 7: Multi-Sample Performance & Caching Consistency Profile ──────
    sample_times: list[float] = [round(landing.elapsed_ms, 3)]
    for _ in range(max(0, perf_samples - 1)):
        s_resp = requester(target_url, method="GET", headers=default_headers, timeout=timeout, follow_redirects=True, use_environment_proxies=False)
        if s_resp.status_code > 0:
            sample_times.append(round(s_resp.elapsed_ms, 3))

    perf_stats = compute_latency_stats(sample_times)
    perf_checks = [
        f"samples:{perf_stats['count']}",
        f"p50:{perf_stats['p50_ms']}ms",
        f"p95:{perf_stats['p95_ms']}ms",
        f"html_bytes:{len(landing.body)}",
    ]
    cache_control = landing.header("cache-control") or ""
    if cache_control:
        perf_checks.append("cache_control_present")
    else:
        findings.append({"severity": "LOW", "pillar": "Performance", "message": "Missing Cache-Control header on landing page"})

    perf_failures: list[str] = []
    if perf_stats["p95_ms"] > 5000.0:
        perf_failures.append(f"Landing page P95 latency {perf_stats['p95_ms']}ms exceeded 5000ms threshold")
    if len(landing.body) > 500_000:
        perf_failures.append(f"Initial HTML document size ({len(landing.body)} bytes) exceeded 500 KB budget")

    records.append(
        EvidenceRecord(
            test_id="pillar-7.performance-and-caching-profile",
            status="FAIL" if perf_failures else "PASS",
            observed_at=utc_now(),
            target=redacted_target,
            details={
                "suite": suite_name,
                "case_name": "Pillar 7 — Multi-Sample Performance, Payload & Cache Profile",
                "tags": ["performance", "web"],
                "http_method": "GET",
                "status_code": landing.status_code,
                "elapsed_ms": perf_stats["p50_ms"],
                "checks_passed": perf_checks,
                "failure_reasons": perf_failures,
                "latency_profile": perf_stats,
                "html_bytes": len(landing.body),
                "cache_control": cache_control,
            },
        )
    )

    # ── PILLAR 8 (Optional): Live Headless Browser SPA DOM & Core Web Vitals ──
    spa_rendered_links: list[str] = []
    if include_spa_audit:
        from .spa_audit import build_spa_audit_record

        spa_rec = build_spa_audit_record(
            target_url,
            suite_name=suite_name,
            timeout_s=int(max(15, timeout)),
            extra_headers=extra_headers,
        )
        records.append(spa_rec)
        spa_rendered_links = list(spa_rec.details.get("rendered_links") or [])

    # ── PILLAR 9 (Optional): Modern Web, API & Mobile App-Link Security ───────
    if include_modern_security:
        p9_rec, p9_findings = _audit_modern_security_and_applinks(
            target_url,
            base_url,
            origin_host,
            dom,
            requester,
            default_headers,
            timeout,
        )
        records.append(p9_rec)
        findings.extend(p9_findings)

    # ── RESPONSIVE MATRIX (Optional): Desktop / Tablet / Mobile Viewports ─────
    if include_responsive_audit:
        from .spa_audit import build_responsive_audit_record

        records.append(
            build_responsive_audit_record(
                target_url,
                suite_name=suite_name,
                timeout_s=int(max(15, timeout)),
            )
        )

    # ── MULTI-PAGE CRAWLER (Optional): Sitemap + SPA + BFS Internal Page Audit ─
    if crawl_max_pages > 1:
        crawl_rec, crawl_findings = _run_multipage_crawl(
            target_url,
            base_url,
            origin_host,
            dom,
            sitemap_body,
            extra_seed_links=spa_rendered_links,
            max_pages=crawl_max_pages,
            requester=requester,
            default_headers=default_headers,
            timeout=timeout,
        )
        records.append(crawl_rec)
        findings.extend(crawl_findings)

    if code == "id":
        findings = [
            {**f, "message": translate_finding_or_reason(str(f.get("message", "")), code)}
            for f in findings
        ]

    manifest_path: Path | None = None
    manifest_sha: str | None = None
    summary_path: Path | None = None

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = output_dir / "evidence-manifest.json"
        manifest_sha = write_manifest(records, manifest_path)

    analytics = analyze_records(records, manifest_sha256=manifest_sha)

    if output_dir is not None:
        summary_path = output_dir / "suite-summary.json"
        summary_path.write_text(
            json.dumps(
                {
                    "suite_name": suite_name,
                    "target_url": target_url,
                    "language": code,
                    "manifest_path": str(manifest_path),
                    "manifest_sha256": manifest_sha,
                    "analytics": analytics,
                    "findings": findings,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        report_title = f"{'Audit Mendalam SAQA' if code == 'id' else 'SAQA Deep Audit'} — {parsed.hostname}"
        (output_dir / "report.html").write_text(
            render_html_report(analytics, records, manifest_sha256=manifest_sha, title=report_title, lang=code),
            encoding="utf-8",
        )
        (output_dir / "report.md").write_text(
            render_markdown_report(analytics, title=report_title, lang=code),
            encoding="utf-8",
        )
        render_pdf_report(
            analytics,
            records,
            output_dir / "qa-executive-report.pdf",
            manifest_sha256=manifest_sha,
            title=report_title,
            lang=code,
        )
        (output_dir / "junit.xml").write_text(
            render_junit_xml(analytics, records, suite_name=suite_name),
            encoding="utf-8",
        )
        (output_dir / "results.sarif").write_text(
            json.dumps(render_sarif_report(records, suite_name=suite_name), indent=2),
            encoding="utf-8",
        )
        render_scorecard_png(analytics, records, output_dir / "qa-scorecard.png", title=f"SAQA DEEP AUDIT | {parsed.hostname}", lang=code)
        render_analytics_svg(analytics, records, output_dir / "qa-analytics-chart.svg", title=report_title, lang=code)
        export_csv_matrix(records, output_dir / "qa-test-matrix.csv", lang=code)

    return DeepAuditResult(
        target_url=target_url,
        records=tuple(records),
        analytics=analytics,
        findings=tuple(findings),
        manifest_path=manifest_path,
        manifest_sha256=manifest_sha,
        summary_path=summary_path,
    )

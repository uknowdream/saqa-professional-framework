"""Comprehensive v2.7.0 tests: Agile/Waterfall Governance, RTM, Binary AXML, Anti-SSRF, XXE, PDF Compression & Jira Retry."""
from __future__ import annotations

import re
import struct
import zipfile
import zlib
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from saqa.analytics import analyze_records
from saqa.api import ApiResponse
from saqa.cli import main as cli_main
from saqa.evidence import EvidenceRecord, utc_now, write_manifest
from saqa.http_pool import create_pooled_requester
from saqa.jira import JiraClient, JiraConfig, JiraIssueResult, JiraIssueState, JiraProjectResult
from saqa.jira_sync import sync_manifest_to_jira, sync_records_to_jira
from saqa.methodology import (
    WIB,
    build_rtm_matrix,
    classify_defect_severity,
    compute_waterfall_timeline_window,
    evaluate_methodology_governance,
    export_rtm_csv,
    normalize_methodology,
    render_release_signoff_markdown,
)
from saqa.mobile_audit import audit_mobile_package, parse_android_axml_manifest
from saqa.notifications import dispatch_notifications
from saqa.pdf_report import render_pdf_report
from saqa.spa_audit import build_spa_audit_record
from saqa.ssrf import (
    host_is_private_or_local,
    is_private_or_metadata_ip,
    safe_parse_xml,
    validate_safe_outbound_url,
)
from saqa.web_audit import run_deep_web_audit


def _build_minimal_binary_axml(
    strings: list[str],
    elements: list[tuple[str, list[tuple[str, int, int]]]],
    *,
    utf8: bool = True,
) -> bytes:
    """Construct a valid Android Binary XML (AXML) buffer for testing struct-level parsing."""
    str_index = {s: idx for idx, s in enumerate(strings)}

    # 1. Build StringPool chunk (type 0x0001)
    encoded_strings = bytearray()
    offsets: list[int] = []
    for s in strings:
        offsets.append(len(encoded_strings))
        if utf8:
            raw = s.encode("utf-8")
            encoded_strings.append(len(s) & 0x7F)
            encoded_strings.append(len(raw) & 0x7F)
            encoded_strings.extend(raw)
            encoded_strings.append(0)
        else:
            raw = s.encode("utf-16le")
            encoded_strings.extend(struct.pack("<H", len(s)))
            encoded_strings.extend(raw)
            encoded_strings.extend(b"\x00\x00")
    while len(encoded_strings) % 4 != 0:
        encoded_strings.append(0)

    flags = 0x00000100 if utf8 else 0x00000000
    header_size = 28
    strings_start = header_size + 4 * len(strings)
    pool_size = strings_start + len(encoded_strings)
    pool_chunk = bytearray()
    pool_chunk.extend(struct.pack("<HHIIIIII", 0x0001, header_size, pool_size, len(strings), 0, flags, strings_start, 0))
    for off in offsets:
        pool_chunk.extend(struct.pack("<I", off))
    pool_chunk.extend(encoded_strings)

    # 2. Build START_ELEMENT (0x0102) + END_ELEMENT (0x0103) chunks
    body = bytearray()
    for tag_name, attrs in elements:
        tag_idx = str_index[tag_name]
        attr_bytes = bytearray()
        for attr_name, val_type, val_data in attrs:
            name_idx = str_index[attr_name]
            raw_val_idx = val_data if val_type == 0x03 else 0xFFFFFFFF
            attr_bytes.extend(struct.pack("<IIIHBBI", 0xFFFFFFFF, name_idx, raw_val_idx, 8, 0, val_type, val_data))
        start_chunk_size = 36 + len(attr_bytes)
        body.extend(
            struct.pack(
                "<HHIIIIIHHHHHH",
                0x0102,
                16,
                start_chunk_size,
                1,
                0xFFFFFFFF,
                0xFFFFFFFF,
                tag_idx,
                20,
                20,
                len(attrs),
                0,
                0,
                0,
            )
        )
        body.extend(attr_bytes)
        body.extend(struct.pack("<HHIIIII", 0x0103, 16, 24, 1, 0xFFFFFFFF, 0xFFFFFFFF, tag_idx))

    total_size = 8 + len(pool_chunk) + len(body)
    return struct.pack("<HHI", 0x0003, 8, total_size) + bytes(pool_chunk) + bytes(body)


def test_binary_axml_decoder_utf8_and_utf16_boolean_flags_and_exported(tmp_path: Path) -> None:
    """Verify true struct-level AXML parsing catches binary boolean flags & unprotected exported components."""
    strings = [
        "manifest",
        "package",
        "com.client.fintech",
        "http://schemas.android.com/apk/res/android",
        "uses-permission",
        "name",
        "android.permission.CAMERA",
        "application",
        "debuggable",
        "usesCleartextTraffic",
        "allowBackup",
        "service",
        "exported",
        "com.client.fintech.SyncService",
    ]
    elements = [
        ("manifest", [("package", 0x03, strings.index("com.client.fintech"))]),
        ("uses-permission", [("name", 0x03, strings.index("android.permission.CAMERA"))]),
        (
            "application",
            [
                ("debuggable", 0x12, 0xFFFFFFFF),
                ("usesCleartextTraffic", 0x12, 1),
                ("allowBackup", 0x12, 1),
            ],
        ),
        (
            "service",
            [
                ("name", 0x03, strings.index("com.client.fintech.SyncService")),
                ("exported", 0x12, 0xFFFFFFFF),
            ],
        ),
    ]

    for use_utf8 in (True, False):
        axml = _build_minimal_binary_axml(strings, elements, utf8=use_utf8)
        parsed = parse_android_axml_manifest(axml)
        assert parsed["format"] == "axml-binary"
        assert parsed["package_name"] == "com.client.fintech"
        assert parsed["debuggable"] is True
        assert parsed["uses_cleartext_traffic"] is True
        assert parsed["allow_backup"] is True
        assert "android.permission.CAMERA" in parsed["permissions"]
        assert any("SyncService" in item for item in parsed["unprotected_exported_components"])

    # End-to-end APK audit with binary AXML triggers debuggable + cleartext failure
    apk = tmp_path / "binary-axml.apk"
    axml_bytes = _build_minimal_binary_axml(strings, elements, utf8=True)
    with zipfile.ZipFile(apk, "w") as zf:
        zf.writestr("AndroidManifest.xml", axml_bytes)
        zf.writestr("META-INF/CERT.RSA", b"signature")
        zf.writestr("lib/arm64-v8a/libcore.so", b"elf")

    res = audit_mobile_package(apk, output_dir=tmp_path / "out", lang="id")
    assert res.passed is False
    assert res.metadata["package_name"] == "com.client.fintech"
    p2 = next(r for r in res.records if r.test_id == "mobile-2.manifest-and-transport-security")
    assert p2.status == "FAIL"
    assert any("debuggable" in f for f in p2.details["failure_reasons"])
    assert any("exported" in w.lower() for w in p2.details["warnings"])


def test_ssrf_guards_xml_xxe_http_pool_redirects_and_telegram_redaction(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify Anti-SSRF blocks metadata/private IPs, XXE blocks DOCTYPE, and Telegram redacts bot token."""
    assert is_private_or_metadata_ip("169.254.169.254") is True
    assert is_private_or_metadata_ip("127.0.0.1") is True
    assert is_private_or_metadata_ip("10.0.0.5") is True
    assert is_private_or_metadata_ip("::1") is True
    assert is_private_or_metadata_ip("93.184.216.34") is False
    assert host_is_private_or_local("metadata.google.internal") is True

    with pytest.raises(ValueError, match="SSRF blocked"):
        validate_safe_outbound_url("http://169.254.169.254/latest/meta-data/", allow_private=False, resolve_dns=False)

    with pytest.raises(ValueError, match="DOCTYPE"):
        safe_parse_xml('<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe "pwn">]><root>&xxe;</root>')

    root = safe_parse_xml("<urlset><url><loc>https://example.test/a</loc></url></urlset>")
    assert root.tag == "urlset"

    # Hop-by-hop redirect from public host -> cloud metadata IP must be blocked!
    seen_headers: list[dict[str, str]] = []

    def mock_handler(req: httpx.Request) -> httpx.Response:
        seen_headers.append(dict(req.headers))
        if req.url.host == "public.example" and req.url.path == "/to-meta":
            return httpx.Response(302, headers={"Location": "http://169.254.169.254/latest/meta-data/"})
        if req.url.host == "public.example" and req.url.path == "/to-other":
            return httpx.Response(302, headers={"Location": "https://93.184.216.34/landing"})
        return httpx.Response(200, text="ok")

    with create_pooled_requester(block_private_redirects=True, transport=httpx.MockTransport(mock_handler)) as pool_req:
        resp_ssrf = pool_req("https://public.example/to-meta", follow_redirects=True)
        assert resp_ssrf.status_code == 0
        assert "ssrf blocked" in (resp_ssrf.error or "").lower()

        seen_headers.clear()
        resp_ok = pool_req(
            "https://public.example/to-other",
            headers={"Authorization": "Bearer secret", "Cookie": "sid=1"},
            follow_redirects=True,
        )
        assert resp_ok.status_code == 200
        assert len(seen_headers) == 2
        assert "authorization" not in {k.lower() for k in seen_headers[1]}
        assert "cookie" not in {k.lower() for k in seen_headers[1]}

    # Notifications block private/metadata webhook URLs AND redact Telegram bot token on failure
    import urllib.error
    import urllib.request

    analytics = {"overall_status": "FAIL", "health_score": 40, "health_grade": "F", "pass_rate_pct": 0.0, "status_counts": {"PASS": 0, "FAIL": 1, "BLOCKED": 0}, "latency": {"p95_ms": 100.0}}
    with pytest.raises(ValueError, match="SSRF blocked"):
        dispatch_notifications(
            analytics,
            suite_name="sec-test",
            webhook_urls=["http://169.254.169.254/hook"],
        )

    def failing_urlopen(req: Any, timeout: float = 10.0) -> Any:
        raise urllib.error.URLError(f"Connection failed to {req.full_url}")

    monkeypatch.setattr(urllib.request, "urlopen", failing_urlopen)
    tg_res = dispatch_notifications(
        analytics,
        suite_name="sec-test",
        webhook_urls=["https://api.telegram.org/bot123456:SUPERSECRET/sendMessage?chat_id=99"],
    )
    assert tg_res[0]["ok"] is False
    assert "SUPERSECRET" not in str(tg_res[0]["error"])
    assert "/bot<REDACTED>/" in str(tg_res[0]["error"])


def test_agile_and_waterfall_methodology_rtm_signoff_and_jira_single_scan(tmp_path: Path) -> None:
    """Verify Agile DoD, Waterfall sequential Stage Gates & dates, RTM, and single-scan zero-duplicate Jira sync."""
    assert normalize_methodology("scrum") == "agile"
    assert normalize_methodology("v-model") == "waterfall"
    with pytest.raises(ValueError, match="Unsupported methodology"):
        normalize_methodology("chaos")

    # Waterfall non-overlapping sequential stage dates
    today = datetime(2026, 11, 27, tzinfo=WIB)
    epic_dates, domain_dates = compute_waterfall_timeline_window(
        today=today,
        sprint_start="2026-11-01",
        sprint_end="2026-11-30",
    )
    assert epic_dates["PHASE-1"][1] < epic_dates["PHASE-2"][0]
    assert epic_dates["PHASE-2"][1] < epic_dates["PHASE-3"][0]
    assert len(domain_dates) == 9

    recs = [
        EvidenceRecord("pillar-1.tls-and-certificate", "PASS", utc_now(), "https://client.test", {"case_name": "Pillar 1 — TLS/SSL Protocol & Certificate Expiry Audit", "tags": ["tls", "security"], "elapsed_ms": 40.0, "checks_passed": ["tls13"]}),
        EvidenceRecord("pillar-2.security-headers", "PASS", utc_now(), "https://client.test", {"case_name": "Pillar 2 — OWASP Security Headers & Cookie Hygiene Audit", "tags": ["security", "headers"], "elapsed_ms": 35.0, "checks_passed": ["hsts"]}),
        EvidenceRecord("pillar-3.accessibility-wcag", "PASS", utc_now(), "https://client.test", {"case_name": "Pillar 3 — WCAG 2.2 Semantic DOM Accessibility Audit", "tags": ["a11y"], "elapsed_ms": 30.0, "checks_passed": ["lang"]}),
        EvidenceRecord("pillar-5.broken-links-and-assets", "PASS", utc_now(), "https://client.test", {"case_name": "Pillar 5 — Automated Broken Link, Static Asset & Mixed-Content Crawler", "tags": ["web", "assets"], "elapsed_ms": 50.0, "checks_passed": ["zero_broken"]}),
        EvidenceRecord("pillar-7.performance-and-caching-profile", "PASS", utc_now(), "https://client.test", {"case_name": "Pillar 7 — Multi-Sample Performance, Payload & Cache Profile", "tags": ["performance"], "elapsed_ms": 45.0, "checks_passed": ["p95_ok"]}),
    ]
    analytics = analyze_records(recs, manifest_sha256="a" * 64)
    rtm = build_rtm_matrix(recs, manifest_sha256="a" * 64, lang="id")
    assert any(row["req_id"] == "REQ-SEC-01" and row["status"] == "PASS" for row in rtm)

    rtm_csv = export_rtm_csv(rtm, tmp_path / "rtm-matrix.csv", lang="id")
    assert rtm_csv.is_file()
    assert "ID Kebutuhan" in rtm_csv.read_text(encoding="utf-8-sig")

    # Waterfall Stage 1 FAIL blocks Stage 2 & Stage 3!
    wf_blocked = evaluate_methodology_governance(
        {"QA-1": "FAIL", "QA-2": "FAIL", "QA-3": "PASS", "QA-4": "PASS", "QA-5": "PASS", "QA-6": "PASS", "QA-7": "PASS", "QA-8": "PASS", "QA-9": "FAIL"},
        analytics,
        methodology="waterfall",
        lang="id",
    )
    assert wf_blocked["approved"] is False
    assert "NO-GO" in wf_blocked["decision"]
    assert wf_blocked["stage_gates"][0]["status"] == "FAIL"
    assert wf_blocked["stage_gates"][1]["status"] == "BLOCKED"
    assert wf_blocked["stage_gates"][2]["status"] == "BLOCKED"

    # Defect severity classification
    p0 = classify_defect_severity("QA-5", [{"status": "FAIL", "details": {}}], lang="id")
    assert p0["severity"] == "P0-Blocker"
    assert p0["priority"] == "Highest"

    # Sign-off markdown
    signoff = render_release_signoff_markdown(wf_blocked, rtm, analytics, suite_name="client-uat", manifest_sha256="a" * 64, lang="id")
    assert "Berita Acara Sertifikasi Rilis" in signoff
    assert "REQ-SEC-01" in signoff

    # Fake Jira client verifying: (1) find_project_issues called ONLY ONCE per sync,
    # (2) switching waterfall -> agile -> EN -> ID produces ZERO duplicate Epics!
    class CountingFakeJira:
        def __init__(self) -> None:
            self.issues: dict[str, JiraIssueResult] = {}
            self.labels: dict[str, set[str]] = {}
            self.uploads: list[tuple[str, str]] = []
            self.find_calls = 0
            self.epics_created = 0
            self._seq = 0

        def verify_access(self) -> JiraProjectResult:
            return JiraProjectResult(key="QA", name="QA Control Plane", project_type="software")

        def get_myself_account_id(self) -> str:
            return "acc-1"

        def find_project_issues(self) -> dict[str, JiraIssueResult]:
            self.find_calls += 1
            return dict(self.issues)

        def create_epic(self, summary: str, description_adf: dict[str, Any], labels: list[str], **kw) -> JiraIssueResult:
            self._seq += 1
            self.epics_created += 1
            res = JiraIssueResult(key=f"QA-{self._seq}", id=str(self._seq), url=f"https://jira.test/browse/QA-{self._seq}")
            self.issues[summary] = res
            self.labels[res.key] = set(labels)
            return res

        def create_task(self, summary: str, description: str, labels: list[str]) -> JiraIssueResult:
            self._seq += 1
            res = JiraIssueResult(key=f"QA-{self._seq}", id=str(self._seq), url=f"https://jira.test/browse/QA-{self._seq}")
            self.issues[summary] = res
            self.labels[res.key] = set(labels)
            return res

        def get_issue_state(self, issue_key: str) -> JiraIssueState:
            return JiraIssueState(key=issue_key, status="To Do", labels=tuple(sorted(self.labels.get(issue_key, set()))))

        def update_labels(self, issue_key: str, add=(), remove=()) -> None:
            lbls = self.labels.setdefault(issue_key, set())
            lbls.update(add)
            lbls.difference_update(remove)

        def update_issue_fields(self, issue_key: str, fields: dict[str, Any]) -> None:
            new_sum = fields.get("summary")
            if new_sum:
                for old_s, res in list(self.issues.items()):
                    if res.key == issue_key and old_s != new_sum:
                        del self.issues[old_s]
                        self.issues[new_sum] = res

        def transition_to_any(self, issue_key: str, targets: tuple[str, ...]) -> str | None:
            return targets[0] if targets else None

        def add_adf_comment_once(self, issue_key: str, adf: dict[str, Any], marker: str) -> bool:
            return True

        def upload_attachment(self, issue_key: str, file_path: Path) -> dict[str, Any]:
            self.uploads.append((issue_key, file_path.name))
            return {"filename": file_path.name}

        def close(self) -> None:
            pass

    fake = CountingFakeJira()
    m_path = tmp_path / "evidence-manifest.json"
    write_manifest(recs, m_path, signing_key="secret-k")

    # 1st sync: Waterfall + Indonesian
    s1 = sync_manifest_to_jira(m_path, lang="id", methodology="waterfall", client=fake)  # type: ignore[arg-type]
    assert fake.find_calls == 1
    assert fake.epics_created == 3
    assert s1["methodology"] == "waterfall"
    assert s1["hmac_sha256"] is not None
    assert "rtm-matrix.csv" in s1["attachment_names"]
    assert "release-signoff.md" in s1["attachment_names"]
    assert "qa-executive-report.pdf" in s1["attachment_names"]

    # 2nd sync: Switch to Agile + English -> ZERO new Epics created!
    s2 = sync_records_to_jira(recs, suite_name="client-uat", manifest_sha256="a" * 64, lang="en", methodology="agile", artifact_dir=tmp_path, client=fake)  # type: ignore[arg-type]
    assert fake.find_calls == 2
    assert fake.epics_created == 3  # Strictly reused all 3 Epics!
    assert s2["methodology"] == "agile"
    assert s2["governance"]["approved"] is True


def test_jira_attachment_retry_on_429_and_jql_label_escaping(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify Jira upload_attachment retries HTTP 429 honoring Retry-After and escapes JQL labels."""
    attempts = {"upload": 0, "jql": ""}
    sample = tmp_path / "shot.png"
    sample.write_bytes(b"\x89PNG\r\n\x1a\nfake")

    def fake_post(url: str, **kw) -> httpx.Response:
        attempts["upload"] += 1
        if attempts["upload"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, text="rate limited", request=httpx.Request("POST", url))
        return httpx.Response(200, json=[{"id": "10", "filename": "shot.png"}], request=httpx.Request("POST", url))

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/search/jql"):
            attempts["jql"] = req.url.params.get("jql", "")
            return httpx.Response(200, json={"issues": []})
        return httpx.Response(200, json={"fields": {"attachment": []}})

    monkeypatch.setattr(httpx, "post", fake_post)
    cfg = JiraConfig(base_url="https://jira.example", email="qa@example.test", api_token="tok", project_key="QA")  # noqa: S106
    client = JiraClient(cfg, retry_backoff_s=0.0)
    client._client.close()
    client._client = httpx.Client(base_url=cfg.base_url, transport=httpx.MockTransport(handler))
    try:
        res = client.upload_attachment("QA-1", sample)
        assert res is not None
        assert res["filename"] == "shot.png"
        assert attempts["upload"] == 2

        client.find_project_issues_by_label('bad"label\\x')
        assert r'labels = "bad\"label\\x"' in attempts["jql"]
    finally:
        client.close()


def test_pdf_flatedecode_word_wrap_governance_and_spa_contrast_and_sitemapindex(tmp_path: Path) -> None:
    """Verify compressed multi-line wrapped PDF, WCAG contrast audit warning, and nested sitemapindex expansion."""
    long_rec = EvidenceRecord(
        "pillar-2.long-scenario",
        "FAIL",
        utc_now(),
        "https://example.test",
        {
            "case_name": "Pillar 2 — Extremely Detailed Enterprise Security Headers Verification Across All Subdomains",
            "elapsed_ms": 55.0,
            "failure_reasons": ["Very long failure description that should cleanly wrap across lines inside the compressed PDF stream without breaking layout"],
        },
    )
    stats = analyze_records([long_rec], manifest_sha256="c" * 64)
    gov = evaluate_methodology_governance({"QA-1": "FAIL", "QA-2": "PASS", "QA-3": "PASS", "QA-4": "PASS", "QA-5": "FAIL", "QA-6": "PASS", "QA-7": "PASS", "QA-8": "PASS", "QA-9": "FAIL"}, stats, methodology="waterfall", lang="en")
    pdf_bytes = render_pdf_report(stats, [long_rec], tmp_path / "wf.pdf", manifest_sha256="c" * 64, hmac_sha256="d" * 64, methodology="waterfall", governance=gov, lang="en")
    assert b"/Filter /FlateDecode" in pdf_bytes
    decompressed = b"\n".join(
        zlib.decompress(m.group(1))
        for m in re.finditer(rb"stream\n(.*?)\nendstream", pdf_bytes, flags=re.DOTALL)
    )
    assert b"WATERFALL" in decompressed
    assert b"NO-GO" in decompressed
    assert b"Page 1 of 1" in decompressed

    # WCAG 2.2 AA contrast audit surfaced cleanly from SPA inspector
    def mock_spa_inspector(url: str, **kw) -> dict[str, Any]:
        return {
            "engine": "playwright-chromium",
            "available": True,
            "wall_ms": 320.0,
            "rendered_html": '<html lang="en"><head><title>App</title></head><body><main><h1>Hello</h1></main></body></html>',
            "dom_node_count": 42,
            "console_errors": [],
            "page_errors": [],
            "failed_requests": [],
            "navigation_timing": {"ttfb_ms": 50.0},
            "web_vitals": {"fcp_ms": 180.0, "lcp_ms": 420.0, "cls": 0.01},
            "asset_budget": {"total_transfer_kb": 120.0, "resource_count": 12},
            "contrast_audit": {"checked": 20, "low_contrast_count": 2, "samples": ["a:2.1"]},
        }

    spa_rec = build_spa_audit_record("https://spa.test/", suite_name="spa", inspector=mock_spa_inspector)
    assert spa_rec.status == "PASS"
    assert spa_rec.details["web_vitals"]["lcp_ms"] == 420.0
    assert any("WCAG 2.2 AA low color contrast" in w for w in spa_rec.details["warnings"])

    # Nested <sitemapindex> expansion inside deep-audit multi-page crawler
    html_root = '<!doctype html><html lang="en"><head><title>Home</title><meta name="viewport" content="width=device-width,initial-scale=1"/><meta name="description" content="desc"/><link rel="canonical" href="https://site.test/"/><meta property="og:title" content="t"/><meta property="og:description" content="d"/></head><body><main><h1>Home</h1></main></body></html>'
    html_sub = '<!doctype html><html lang="en"><head><title>About</title><meta name="viewport" content="width=device-width,initial-scale=1"/><meta name="description" content="about"/></head><body><main><h1>About</h1></main></body></html>'
    s_index = '<?xml version="1.0"?><sitemapindex><sitemap><loc>https://site.test/sitemap-pages.xml</loc></sitemap></sitemapindex>'
    s_child = '<?xml version="1.0"?><urlset><url><loc>https://site.test/about</loc></url></urlset>'

    def site_req(url: str, **kw) -> ApiResponse:
        if url.endswith("/sitemap.xml"):
            return ApiResponse(200, {"Content-Type": "application/xml"}, s_index.encode(), 10.0)
        if url.endswith("/sitemap-pages.xml"):
            return ApiResponse(200, {"Content-Type": "application/xml"}, s_child.encode(), 10.0)
        if url.endswith("/about"):
            return ApiResponse(200, {"Content-Type": "text/html"}, html_sub.encode(), 15.0)
        if url.endswith(("/.env", "/.git/HEAD")):
            return ApiResponse(404, {}, b"not found", 5.0)
        return ApiResponse(
            200,
            {
                "Content-Type": "text/html",
                "Strict-Transport-Security": "max-age=31536000",
                "Content-Security-Policy": "default-src 'self'",
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Referrer-Policy": "no-referrer",
                "Cache-Control": "public, max-age=60",
            },
            html_root.encode(),
            20.0,
        )

    audit = run_deep_web_audit(
        "https://site.test/",
        output_dir=tmp_path / "site-audit",
        crawl_max_pages=4,
        requester=site_req,
        tls_inspector=lambda host, port=443, timeout=10.0: {"tls_version": "TLSv1.3", "days_remaining": 90, "subject": host, "issuer": "CA"},
    )
    crawl_rec = next(r for r in audit.records if r.test_id == "multi-page.site-crawl-audit")
    assert crawl_rec.status == "PASS"
    assert any("/about" in p["url"] for p in crawl_rec.details["pages"])

    # CLI report command supports --methodology waterfall
    pdf_cli = tmp_path / "cli-wf.pdf"
    rc = cli_main(["report", str(tmp_path / "site-audit" / "evidence-manifest.json"), "--pdf", str(pdf_cli), "--methodology", "waterfall", "--lang", "id"])
    assert rc == 0
    assert pdf_cli.is_file()

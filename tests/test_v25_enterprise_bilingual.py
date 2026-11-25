"""Comprehensive unit & integration tests for SAQA v2.5.0 Enterprise & Bilingual (EN/ID) features."""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx
import pytest

from saqa.analytics import analyze_records
from saqa.api import ApiResponse
from saqa.cli import main as cli_main
from saqa.evidence import EvidenceRecord, utc_now, write_manifest
from saqa.i18n import get_all_summary_variants, get_issue_summaries, normalize_lang, tr
from saqa.jira import JiraClient, JiraConfig, JiraIssueResult, JiraIssueState, JiraProjectResult
from saqa.jira_sync import sync_manifest_to_jira
from saqa.reporting import render_html_report, render_junit_xml, render_markdown_report, render_sarif_report
from saqa.spa_audit import build_responsive_audit_record, build_spa_audit_record, load_journey_file, run_browser_journey
from saqa.visual_diff import compare_png_images, parse_mask_spec
from saqa.visual_evidence import _Canvas, _encode_rgb_png, capture_viewport_matrix
from saqa.web_audit import run_deep_web_audit


def test_i18n_normalization_and_translations(monkeypatch: pytest.MonkeyPatch) -> None:
    assert normalize_lang("en") == "en"
    assert normalize_lang("English") == "en"
    assert normalize_lang("id") == "id"
    assert normalize_lang("id-ID") == "id"
    assert normalize_lang("indonesia") == "id"
    assert normalize_lang("bahasa") == "id"

    monkeypatch.setenv("SAQA_LANG", "id")
    assert normalize_lang(None) == "id"
    monkeypatch.delenv("SAQA_LANG", raising=False)

    with pytest.raises(ValueError, match="Unsupported language"):
        normalize_lang("fr")

    en_sums = get_issue_summaries("en")
    id_sums = get_issue_summaries("id")
    assert en_sums["QA-1"] == "SAQA | Test Management Foundation"
    assert id_sums["QA-1"] == "SAQA | Fondasi Manajemen Pengujian"
    assert len(get_all_summary_variants("QA-1")) == 2
    assert "Ringkasan Eksekutif" in tr("sec_1_exec", "id")


def test_bilingual_jira_sync_en_to_id_and_back_without_duplicates_plus_waivers_and_agile_sprint(tmp_path: Path) -> None:
    class BilingualAgileJiraStub:
        def __init__(self) -> None:
            self.config = JiraConfig("https://jira.example", "qa@example.com", "tok", "QA")
            self.issues_by_key: dict[str, dict] = {}
            self.sprint_moves: list[tuple[int, list[str]]] = []
            self.created_bugs: list[str] = []
            self.attachments: list[tuple[str, str]] = []
            self.counter = 0

            # Pre-seed QA-1..QA-9 in English; mark QA-5 as waived by QA Lead ('accepted-risk')
            for idx, (k, s) in enumerate(get_issue_summaries("en").items(), start=1):
                lbls = ["saqa-bootstrap", "saqa-automation", f"saqa-{k.lower()}"]
                if k == "QA-5":
                    lbls.append("accepted-risk")
                self.issues_by_key[k] = {"id": str(idx), "summary": s, "status": "To Do", "labels": lbls}

        def verify_access(self) -> JiraProjectResult:
            return JiraProjectResult("QA", "Client Quality", "software")

        def get_myself_account_id(self) -> str:
            return "acc-99"

        def find_active_sprint(self) -> dict:
            return {
                "id": 77,
                "name": "Sprint 12 — Mobile & Web Release",
                "board_id": 5,
                "startDate": "2026-11-15T00:00:00.000Z",
                "endDate": "2026-11-30T00:00:00.000Z",
            }

        def move_issues_to_sprint(self, sprint_id: int, issue_keys) -> bool:
            self.sprint_moves.append((sprint_id, list(issue_keys)))
            return True

        def find_project_issues(self) -> dict[str, JiraIssueResult]:
            return {
                info["summary"]: JiraIssueResult(k, info["id"], f"https://jira.example/browse/{k}")
                for k, info in self.issues_by_key.items()
            }

        def find_project_issues_by_label(self, label: str) -> list[JiraIssueResult]:
            return [
                JiraIssueResult(k, info["id"], f"https://jira.example/browse/{k}")
                for k, info in self.issues_by_key.items()
                if label in info["labels"]
            ]

        def create_epic(self, summary, description_adf, labels, **kwargs) -> JiraIssueResult:
            self.counter += 1
            key = f"QA-{20 + self.counter}"
            self.issues_by_key[key] = {"id": str(20 + self.counter), "summary": summary, "status": "To Do", "labels": list(labels)}
            return JiraIssueResult(key, str(20 + self.counter), f"https://jira.example/browse/{key}")

        def get_issue_state(self, issue_key: str) -> JiraIssueState:
            info = self.issues_by_key[issue_key]
            return JiraIssueState(issue_key, info["status"], tuple(info["labels"]))

        def update_labels(self, issue_key: str, *, add=(), remove=()) -> None:
            cur = list(self.issues_by_key[issue_key]["labels"])
            for r in remove:
                if r in cur:
                    cur.remove(r)
            for a in add:
                if a not in cur:
                    cur.append(a)
            self.issues_by_key[issue_key]["labels"] = cur

        def update_issue_fields(self, issue_key: str, fields: dict) -> None:
            if "summary" in fields:
                self.issues_by_key[issue_key]["summary"] = fields["summary"]
            self.issues_by_key[issue_key]["last_fields"] = fields

        def transition_to_any(self, issue_key: str, target_statuses) -> str:
            dest = next(iter(target_statuses))
            self.issues_by_key[issue_key]["status"] = dest
            return dest

        def add_adf_comment_once(self, issue_key: str, adf_doc, marker: str) -> bool:
            self.issues_by_key[issue_key]["last_comment"] = adf_doc
            return True

        def create_bug(self, summary: str, description: str, labels: list[str]) -> JiraIssueResult:
            self.counter += 1
            key = f"QA-{50 + self.counter}"
            self.created_bugs.append(summary)
            self.issues_by_key[key] = {"id": str(50 + self.counter), "summary": summary, "status": "Open", "labels": labels}
            return JiraIssueResult(key, str(50 + self.counter), f"https://jira.example/browse/{key}")

        def upload_attachment(self, issue_key: str, file_path: Path, **kwargs):
            self.attachments.append((issue_key, file_path.name))
            return {"id": "1", "filename": file_path.name}

        def close(self) -> None:
            pass

    manifest = tmp_path / "manifest.json"
    write_manifest(
        [
            EvidenceRecord(
                test_id="web-ok",
                status="PASS",
                observed_at=utc_now(),
                target="https://client.id",
                details={"suite": "client-app", "tags": ["web", "api", "a11y"], "elapsed_ms": 80.0},
            ),
            EvidenceRecord(
                test_id="sec-warn",
                status="FAIL",
                observed_at=utc_now(),
                target="https://client.id",
                details={"suite": "client-app", "tags": ["security"], "failure_reasons": ["Missing CSP"]},
            ),
        ],
        manifest,
    )

    stub = BilingualAgileJiraStub()
    # 1. Sync in Bahasa Indonesia ('id')
    res_id = sync_manifest_to_jira(manifest, lang="id", client=stub)  # type: ignore[arg-type]
    assert res_id["language"] == "id"
    assert res_id["active_sprint"]["id"] == 77
    assert stub.sprint_moves[0][0] == 77
    # QA-5 had 'accepted-risk' waiver, so QA-5 AND rollup QA-1/QA-9 become PASS with ZERO auto-bugs!
    assert res_id["waived_domains"] == ["QA-5"]
    by_dom_id = {x["domain"]: x for x in res_id["synced_issues"]}
    assert by_dom_id["QA-5"]["status"] == "PASS"
    assert by_dom_id["QA-5"]["waived"] is True
    assert by_dom_id["QA-9"]["status"] == "PASS"
    assert stub.created_bugs == []
    assert stub.issues_by_key["QA-1"]["summary"] == "SAQA | Fondasi Manajemen Pengujian"
    desc_str = json.dumps(stub.issues_by_key["QA-1"]["last_fields"]["description"])
    assert "Ringkasan Eksekutif Kualitas" in desc_str
    assert "Bahasa Indonesia (ID)" in desc_str
    assert stub.counter == 3  # Exactly the 3 Phase Epics!
    att_names = {n for _, n in stub.attachments}
    assert {"junit.xml", "results.sarif", "report.html", "report.md", "qa-scorecard.png"}.issubset(att_names)

    # 2. Switch back to English ('en') on the exact same project -> ZERO duplicate Epics or Tasks!
    epics_before = [k for k in stub.issues_by_key if k.startswith("QA-2")]
    res_en = sync_manifest_to_jira(manifest, lang="en", client=stub)  # type: ignore[arg-type]
    epics_after = [k for k in stub.issues_by_key if k.startswith("QA-2")]
    assert res_en["language"] == "en"
    assert epics_before == epics_after
    assert stub.issues_by_key["QA-1"]["summary"] == "SAQA | Test Management Foundation"
    desc_en_str = json.dumps(stub.issues_by_key["QA-1"]["last_fields"]["description"])
    assert "Executive Quality & Governance Summary" in desc_en_str


def test_jira_client_agile_sprint_methods() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/rest/agile/1.0/board":
            return httpx.Response(200, json={"values": [{"id": 9, "type": "scrum"}]})
        if req.url.path == "/rest/agile/1.0/board/9/sprint":
            return httpx.Response(200, json={"values": [{"id": 42, "name": "Sprint 42", "startDate": "2026-11-01", "endDate": "2026-11-14"}]})
        if req.url.path == "/rest/agile/1.0/sprint/42/issue" and req.method == "POST":
            return httpx.Response(204)
        return httpx.Response(404)

    cfg = JiraConfig("https://jira.example", "qa@example.com", "sec", "QA")
    client = JiraClient(cfg, timeout=1.0)
    client._client = httpx.Client(transport=httpx.MockTransport(handler), base_url=cfg.base_url)
    try:
        sp = client.find_active_sprint()
        assert sp is not None and sp["id"] == 42 and sp["name"] == "Sprint 42"
        assert client.move_issues_to_sprint(42, ["QA-1", "QA-2"]) is True
    finally:
        client.close()


def test_junit_xml_sarif_and_indonesian_reports() -> None:
    recs = [
        EvidenceRecord(
            test_id="pillar-2.security",
            status="FAIL",
            observed_at=utc_now(),
            target="https://app.example",
            details={"suite": "audit", "elapsed_ms": 125.0, "failure_reasons": ["Invalid XCTO"], "tags": ["security"]},
        ),
        EvidenceRecord(
            test_id="pillar-4.seo",
            status="PASS",
            observed_at=utc_now(),
            target="https://app.example",
            details={"suite": "audit", "elapsed_ms": 40.0, "checks_passed": ["canonical"], "warnings": ["Missing description"]},
        ),
        EvidenceRecord(
            test_id="pillar-8.spa",
            status="BLOCKED",
            observed_at=utc_now(),
            target="https://app.example",
            details={"suite": "audit", "elapsed_ms": 0.0, "failure_reasons": ["No browser"]},
        ),
    ]
    stats = analyze_records(recs, manifest_sha256="f" * 64)

    xml_str = render_junit_xml(stats, recs, suite_name="client-suite")
    root = ET.fromstring(xml_str)
    suite_el = root.find("testsuite")
    assert suite_el is not None
    assert suite_el.attrib["tests"] == "3"
    assert suite_el.attrib["failures"] == "1"
    assert suite_el.attrib["skipped"] == "1"

    sarif = render_sarif_report(recs, suite_name="client-suite")
    assert sarif["version"] == "2.1.0"
    results = sarif["runs"][0]["results"]
    levels = {r["ruleId"]: r["level"] for r in results}
    assert levels["pillar-2.security"] == "error"
    assert levels["pillar-4.seo"] == "warning"

    md_id = render_markdown_report(stats, title="Laporan Klien", lang="id")
    assert "Ringkasan Metrik Kualitas" in md_id
    assert "Tingkat Kelulusan" in md_id

    html_id = render_html_report(stats, recs, title="Laporan Klien", lang="id")
    assert '<html lang="id">' in html_id
    assert "Skor Kesehatan" in html_id
    assert "Distribusi Status Pengujian" in html_id


def test_pillar_9_modern_security_and_multipage_sitemap_bfs_crawler(tmp_path: Path) -> None:
    landing_html = """<!doctype html><html lang="id"><head>
      <title>Beranda Klien</title>
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <meta name="description" content="Situs utama klien" />
      <link rel="canonical" href="https://client.test/" />
      <meta property="og:title" content="Klien" /><meta property="og:description" content="Desc" />
      <script src="https://cdn.thirdparty.example/sdk.js"></script>
    </head><body><main><h1>Selamat Datang</h1><a href="/produk">Produk</a></main></body></html>"""

    subpage_html = """<!doctype html><html lang="id"><head>
      <title>Produk Kami</title>
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <meta name="description" content="Halaman produk" />
    </head><body><main><h1>Daftar Produk</h1><img src="/p.png" alt="Produk" /></main></body></html>"""

    sitemap_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset><url><loc>https://client.test/tentang</loc></url></urlset>"""

    seen_cookies: list[str] = []

    def fake_req(url: str, **kwargs) -> ApiResponse:
        hdrs = kwargs.get("headers") or {}
        if "Cookie" in hdrs:
            seen_cookies.append(hdrs["Cookie"])
        if hdrs.get("Origin") == "https://saqa-cors-probe.invalid":
            # Safe non-reflected CORS
            return ApiResponse(200, {"Content-Type": "text/html"}, landing_html.encode("utf-8"), 15.0)
        if url.endswith("/sitemap.xml"):
            return ApiResponse(200, {"Content-Type": "application/xml"}, sitemap_xml.encode("utf-8"), 12.0)
        if url.endswith(("/produk", "/tentang")):
            return ApiResponse(200, {"Content-Type": "text/html"}, subpage_html.encode("utf-8"), 18.0)
        if url.endswith("/.well-known/security.txt"):
            return ApiResponse(200, {"Content-Type": "text/plain"}, b"Contact: mailto:sec@client.test\n", 10.0)
        if url.endswith("/.well-known/assetlinks.json"):
            return ApiResponse(200, {"Content-Type": "application/json"}, b'[{"relation":["delegate_permission/common.handle_all_urls"]}]', 10.0)
        if url.endswith("/.well-known/apple-app-site-association"):
            return ApiResponse(404, {}, b"", 10.0)
        if "/graphql" in url:
            return ApiResponse(200, {"Content-Type": "application/json"}, b'{"data":{"__schema":{"queryType":{"name":"Query"}}}}', 14.0)
        if url.endswith(("/.env", "/.git/HEAD", "/robots.txt", "/manifest.webmanifest")):
            return ApiResponse(404, {}, b"", 10.0)
        return ApiResponse(
            200,
            {"Content-Type": "text/html", "Strict-Transport-Security": "max-age=31536000", "X-Content-Type-Options": "nosniff", "Cache-Control": "max-age=60"},
            landing_html.encode("utf-8"),
            20.0,
        )

    def fake_tls(host: str, port: int, *, timeout: float = 10.0) -> dict:
        return {
            "hostname": host,
            "port": port,
            "protocol": "TLSv1.3",
            "cipher": "AES256",
            "issuer": "CN=CA",
            "subject": f"CN={host}",
            "san_count": 1,
            "expires_at": "2027-06-01T00:00:00+00:00",
            "days_remaining": 120,
        }

    out = tmp_path / "audit-id"
    res = run_deep_web_audit(
        "https://client.test/",
        output_dir=out,
        perf_samples=1,
        include_modern_security=True,
        crawl_max_pages=4,
        cookies={"session_id": "demo123"},
        lang="id",
        requester=fake_req,
        tls_inspector=fake_tls,
    )
    assert res.passed is True
    assert seen_cookies and "session_id=demo123" in seen_cookies[0]
    by_id = {r.test_id: r for r in res.records}
    assert "pillar-9.modern-web-and-app-security" in by_id
    p9 = by_id["pillar-9.modern-web-and-app-security"]
    assert "rfc9116_security_txt_present" in p9.details["checks_passed"]
    assert "mobile_applink_valid:/.well-known/assetlinks.json" in p9.details["checks_passed"]
    assert len(p9.details["missing_sri_scripts"]) == 1
    assert any("GraphQL Introspection" in w for w in p9.details["warnings"])

    crawl = by_id["multi-page.site-crawl-audit"]
    assert crawl.status == "PASS"
    assert len(crawl.details["pages"]) == 2  # /tentang (from sitemap) + /produk (from link)
    assert (out / "junit.xml").is_file()
    assert (out / "results.sarif").is_file()


def test_visual_diff_masking_and_antialiasing_filter(tmp_path: Path) -> None:
    assert parse_mask_spec("10, 20, 100, 50") == (10, 20, 100, 50)
    with pytest.raises(ValueError, match="mask region"):
        parse_mask_spec("10,20,-5,10")

    base_png = tmp_path / "base.png"
    curr_png = tmp_path / "curr.png"
    diff_png = tmp_path / "diff.png"

    c1 = _Canvas(40, 40, (20, 20, 20))
    c2 = _Canvas(40, 40, (20, 20, 20))
    # Dynamic animated clock/banner inside (5, 5, 10, 10)
    c2.fill_rect(5, 5, 10, 10, (250, 200, 30))
    base_png.write_bytes(_encode_rgb_png(40, 40, c1.pixels))
    curr_png.write_bytes(_encode_rgb_png(40, 40, c2.pixels))

    # Without mask -> fails
    unmasked = compare_png_images(base_png, curr_png, max_mismatch_pct=0.5)
    assert unmasked.passed is False and unmasked.mismatch_pixels == 100

    # With mask covering (5, 5, 10, 10) -> 0 mismatch, PASS!
    masked = compare_png_images(
        base_png,
        curr_png,
        diff_output_path=diff_png,
        max_mismatch_pct=0.5,
        mask_regions=[(5, 5, 10, 10)],
    )
    assert masked.passed is True
    assert masked.mismatch_pixels == 0
    assert masked.masked_pixels == 100
    assert diff_png.is_file()

    # High-contrast 1px edge anti-aliasing check
    aa1 = _Canvas(20, 20, (0, 0, 0))
    aa1.fill_rect(10, 0, 10, 20, (255, 255, 255))
    aa1.fill_rect(9, 5, 1, 10, (128, 128, 128))  # 1px AA ramp on sharp black/white edge
    aa2 = _Canvas(20, 20, (0, 0, 0))
    aa2.fill_rect(10, 0, 10, 20, (255, 255, 255))
    aa2.fill_rect(9, 5, 1, 10, (100, 100, 100))  # Slight OS font AA shift
    p_aa1 = tmp_path / "aa1.png"
    p_aa2 = tmp_path / "aa2.png"
    p_aa1.write_bytes(_encode_rgb_png(20, 20, aa1.pixels))
    p_aa2.write_bytes(_encode_rgb_png(20, 20, aa2.pixels))

    res_aa = compare_png_images(p_aa1, p_aa2, pixel_tolerance=10, max_mismatch_pct=0.0, ignore_antialiasing=True)
    assert res_aa.passed is True
    assert res_aa.antialiased_pixels == 10
    assert res_aa.mismatch_pixels == 0


def test_responsive_audit_cwv_and_browser_journey_handling(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    rec_cwv = build_spa_audit_record(
        "https://client.test/",
        suite_name="cwv-suite",
        inspector=lambda url, **kw: {
            "engine": "playwright-chromium",
            "available": True,
            "wall_ms": 210.0,
            "rendered_html": '<!doctype html><html lang="id"><head><title>App</title></head><body><main><h1>Halo</h1></main></body></html>',
            "dom_node_count": 20,
            "console_errors": [],
            "page_errors": [],
            "failed_requests": [],
            "navigation_timing": {"ttfb_ms": 40},
            "web_vitals": {"fcp_ms": 180, "lcp_ms": 420, "cls": 0.02},
            "asset_budget": {"resource_count": 5, "total_bytes": 42000},
        },
    )
    assert rec_cwv.status == "PASS"
    assert "lcp_ms:420" in rec_cwv.details["checks_passed"]

    rec_resp_fail = build_responsive_audit_record(
        "https://client.test/",
        suite_name="resp-suite",
        inspector=lambda url, timeout_s=25: {
            "engine": "playwright-chromium",
            "available": True,
            "wall_ms": 300.0,
            "viewports": [
                {"viewport": "desktop", "width": 1440, "height": 900, "overflow_px": 0, "small_tap_targets": 0, "rendered": True},
                {"viewport": "mobile", "width": 390, "height": 844, "overflow_px": 64, "small_tap_targets": 3, "rendered": True},
            ],
        },
    )
    assert rec_resp_fail.status == "FAIL"
    assert any("Horizontal layout overflow on mobile" in r for r in rec_resp_fail.details["failure_reasons"])

    # Browser journey validation & graceful BLOCKED fallback when Playwright isn't installed
    j_file = tmp_path / "journey.json"
    j_file.write_text(
        json.dumps({
            "name": "mobile-checkout-journey",
            "base_url": "https://client.test",
            "journeys": [{"id": "j1", "name": "Open Home", "steps": [{"action": "goto", "url": "/"}]}],
        }),
        encoding="utf-8",
    )
    loaded = load_journey_file(j_file)
    monkeypatch.setitem(sys.modules, "playwright", None)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    j_recs, j_stats = run_browser_journey(loaded, output_dir=tmp_path / "j-out")
    assert j_recs[0].status == "BLOCKED"
    assert j_stats["overall_status"] == "BLOCKED"

    # CLI report --lang id --junit --sarif + visual-diff --mask
    m_path = tmp_path / "m.json"
    write_manifest([rec_cwv], m_path)
    junit_out = tmp_path / "out.junit.xml"
    sarif_out = tmp_path / "out.sarif"
    html_out = tmp_path / "out.id.html"
    assert cli_main(["report", str(m_path), "--lang", "id", "--html", str(html_out), "--junit", str(junit_out), "--sarif", str(sarif_out)]) == 0
    assert junit_out.is_file() and sarif_out.is_file()
    assert '<html lang="id">' in html_out.read_text(encoding="utf-8")

    # capture_viewport_matrix unit test with mocked screenshot
    from saqa import visual_evidence

    monkeypatch.setattr(
        visual_evidence,
        "capture_web_screenshot",
        lambda url, dest, **kw: (dest.write_bytes(b"png"), dest)[1],
    )
    shots = capture_viewport_matrix("https://client.test/", tmp_path / "shots")
    assert len(shots) == 3


def test_playwright_spa_responsive_and_interactive_journey_full_flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    from types import ModuleType
    from saqa.spa_audit import inspect_responsive_viewports, inspect_spa_runtime

    class FakePage:
        url = "https://client.test/dashboard"

        def on(self, event: str, handler) -> None:
            return

        def goto(self, url: str, **kw) -> None:
            self.url = url

        def content(self) -> str:
            return '<!doctype html><html lang="id"><head><title>Dashboard</title></head><body><main><h1>Halo Klien</h1></main></body></html>'

        def evaluate(self, script: str, arg=None):
            if "querySelectorAll('*')" in script:
                return 42
            if "overflow_px" in script:
                return {"overflow_px": 0, "small_tap_targets": 0}
            return {
                "navigation_timing": {"ttfb_ms": 25, "dom_interactive_ms": 90, "load_event_ms": 140},
                "web_vitals": {"fcp_ms": 110, "lcp_ms": 220, "cls": 0.01},
                "asset_budget": {"resource_count": 4, "total_bytes": 18000},
            }

        def wait_for_selector(self, selector: str, **kw) -> None:
            return

        def click(self, selector: str, **kw) -> None:
            return

        def fill(self, selector: str, value: str, **kw) -> None:
            return

        def press(self, selector: str, key: str, **kw) -> None:
            return

        def inner_text(self, selector: str, **kw) -> str:
            return "Halo Klien Sukses"

        def is_visible(self, selector: str) -> bool:
            return True

        def screenshot(self, path: str, **kw) -> None:
            Path(path).write_bytes(b"fake-png")

    class FakeContext:
        def add_cookies(self, cookies) -> None:
            return

        def new_page(self) -> FakePage:
            return FakePage()

        def close(self) -> None:
            return

    class FakeBrowser:
        def new_context(self, **kw) -> FakeContext:
            return FakeContext()

        def close(self) -> None:
            return

    class FakePlaywright:
        class chromium:
            @staticmethod
            def launch(**kw) -> FakeBrowser:
                return FakeBrowser()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    fake_pkg = ModuleType("playwright")
    fake_sync = ModuleType("playwright.sync_api")
    fake_sync.sync_playwright = FakePlaywright  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "playwright", fake_pkg)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_sync)

    state_file = tmp_path / "auth.json"
    state_file.write_text("{}", encoding="utf-8")

    spa_info = inspect_spa_runtime(
        "https://client.test/dashboard",
        extra_headers={"X-Client": "1"},
        storage_state=state_file,
    )
    assert spa_info["engine"] == "playwright-chromium"
    assert spa_info["web_vitals"]["lcp_ms"] == 220

    resp_info = inspect_responsive_viewports("https://client.test/dashboard")
    assert resp_info["available"] is True
    assert len(resp_info["viewports"]) == 3

    journey_path = tmp_path / "e2e-journey.json"
    journey_path.write_text(
        json.dumps({
            "name": "client-portal-e2e",
            "base_url": "https://client.test",
            "storage_state": str(state_file),
            "headers": {"X-Trace": "saqa"},
            "cookies": [{"name": "sid", "value": "123", "url": "https://client.test"}],
            "journeys": [
                {
                    "id": "portal-search-flow",
                    "name": "Portal Search & Verify",
                    "user_agent": "SAQA-Mobile-Client/1.0",
                    "steps": [
                        {"action": "goto", "url": "/dashboard"},
                        {"action": "wait_for_selector", "selector": "main"},
                        {"action": "fill", "selector": "#q", "value": "produk"},
                        {"action": "press", "selector": "#q", "key": "Enter"},
                        {"action": "click", "selector": "#btn"},
                        {"action": "scroll", "x": 0, "y": 300},
                        {"action": "assert_text", "selector": "main", "contains": "Halo Klien"},
                        {"action": "assert_visible", "selector": "main"},
                        {"action": "assert_url", "contains": "dashboard"},
                        {"action": "screenshot", "name": "step-final"},
                    ],
                }
            ],
        }),
        encoding="utf-8",
    )
    j_out = tmp_path / "journey-artifacts"
    assert cli_main(["run-journey", str(journey_path), "--output-dir", str(j_out), "--lang", "id"]) == 0
    assert (j_out / "step-final.png").is_file()
    assert (j_out / "evidence-manifest.json").is_file()


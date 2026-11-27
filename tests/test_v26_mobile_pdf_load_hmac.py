"""Unit & integration tests for SAQA v2.6.0: Mobile APK/IPA Auditor, PDF Exporter, Load Tester, HMAC Provenance, & Full ID Translation."""
from __future__ import annotations

import json
import plistlib
import zipfile
from pathlib import Path

import pytest

from saqa.analytics import analyze_records
from saqa.api import ApiResponse
from saqa.cli import main as cli_main
from saqa.evidence import EvidenceRecord, utc_now, verify_manifest, write_manifest
from saqa.i18n import translate_case_name, translate_finding_or_reason
from saqa.load_test import run_load_test
from saqa.mobile_audit import audit_mobile_package
from saqa.pdf_report import render_pdf_report
from saqa.web_audit import run_deep_web_audit


def _build_fake_apk(
    dest: Path,
    *,
    manifest_xml: str,
    signed_release: bool = True,
    debug_cert: bool = False,
    arm32_only: bool = False,
    leaked_secret: str = "",
) -> Path:
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("AndroidManifest.xml", manifest_xml)
        zf.writestr("classes.dex", "dex\n035\x00" + leaked_secret)
        if signed_release:
            zf.writestr("META-INF/CERT.RSA", b"CN=Android Debug" if debug_cert else b"CN=Client Release Cert")
        if arm32_only:
            zf.writestr("lib/armeabi-v7a/libnative.so", b"\x7fELF32")
        else:
            zf.writestr("lib/arm64-v8a/libnative.so", b"\x7fELF64")
    return dest


def _build_fake_ipa(
    dest: Path,
    *,
    allow_http: bool = False,
    empty_camera_desc: bool = False,
) -> Path:
    info: dict = {
        "CFBundleIdentifier": "id.client.mobileapp",
        "CFBundleShortVersionString": "2.6.0",
        "CFBundleVersion": "260",
        "NSCameraUsageDescription": "" if empty_camera_desc else "Digunakan untuk foto profil dan scan QR",
    }
    if allow_http:
        info["NSAppTransportSecurity"] = {"NSAllowsArbitraryLoads": True}
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Payload/ClientApp.app/Info.plist", plistlib.dumps(info, fmt=plistlib.FMT_BINARY))
        zf.writestr("Payload/ClientApp.app/_CodeSignature/CodeResources", b"<plist></plist>")
        zf.writestr("Payload/ClientApp.app/embedded.mobileprovision", b"<key>application-identifier</key>")
    return dest


def test_mobile_audit_android_apk_clean_and_vulnerable_cases(tmp_path: Path) -> None:
    clean_apk = _build_fake_apk(
        tmp_path / "client-prod.apk",
        manifest_xml='<manifest package="id.dreamex.clientapp"><application android:debuggable="false" android:usesCleartextTraffic="false"/></manifest>',
    )
    out_dir = tmp_path / "apk-report"
    res = audit_mobile_package(clean_apk, output_dir=out_dir, lang="id")
    assert res.passed is True
    assert res.platform == "android"
    assert res.metadata["package_name"] == "id.dreamex.clientapp"
    for fname in ("evidence-manifest.json", "qa-executive-report.pdf", "report.html", "report.md", "junit.xml", "results.sarif"):
        assert (out_dir / fname).is_file()

    # Vulnerable APK: debuggable, cleartext HTTP, debug cert, 32-bit only, and embedded Stripe live secret
    fake_stripe = "sk_live_" + ("A1b2C3d4E5f6" * 2)
    bad_apk = _build_fake_apk(
        tmp_path / "client-bad.apk",
        manifest_xml='<manifest package="id.bad.app"><uses-permission android:name="android.permission.READ_SMS"/><application android:debuggable="true" android:usesCleartextTraffic="true"/></manifest>',
        debug_cert=True,
        arm32_only=True,
        leaked_secret=fake_stripe,
    )
    bad_res = audit_mobile_package(bad_apk, lang="id")
    assert bad_res.passed is False
    by_id = {r.test_id: r.status for r in bad_res.records}
    assert by_id["mobile-1.package-integrity-and-signing"] == "FAIL"
    assert by_id["mobile-2.manifest-and-transport-security"] == "FAIL"
    assert by_id["mobile-4.embedded-secrets-and-abi-hygiene"] == "FAIL"


def test_mobile_audit_ios_binary_plist_clean_and_insecure_cases(tmp_path: Path) -> None:
    clean_ipa = _build_fake_ipa(tmp_path / "client-ios.ipa")
    out_ios = tmp_path / "ipa-out"
    assert cli_main(["audit-mobile", str(clean_ipa), "--output-dir", str(out_ios), "--lang", "id"]) == 0
    assert (out_ios / "qa-executive-report.pdf").is_file()

    bad_ipa = _build_fake_ipa(tmp_path / "bad-ios.ipa", allow_http=True, empty_camera_desc=True)
    bad_res = audit_mobile_package(bad_ipa, maestro_flow=tmp_path / "missing.yaml")
    assert bad_res.passed is False
    by_id = {r.test_id: r.status for r in bad_res.records}
    assert by_id["mobile-2.manifest-and-transport-security"] == "FAIL"
    assert by_id["mobile-3.permissions-and-privacy-governance"] == "FAIL"
    assert by_id["mobile-5.maestro-ui-flow"] == "BLOCKED"


def test_pdf_executive_report_multipage_and_valid_pdf_header(tmp_path: Path) -> None:
    # 26 records forces pagination onto Page 2!
    recs = [
        EvidenceRecord(
            test_id=f"pillar-{i}.check",
            status="PASS" if i != 5 else "FAIL",
            observed_at=utc_now(),
            target="https://www.dreamex.tech",
            details={
                "case_name": "Pillar 2 — OWASP Security Headers & Cookie Hygiene Audit",
                "elapsed_ms": float(i * 12),
                "checks_passed": ["hsts"],
                "failure_reasons": [] if i != 5 else ["Missing <meta name='description'>"],
            },
        )
        for i in range(1, 27)
    ]
    stats = analyze_records(recs, manifest_sha256="a" * 64)
    pdf_file = tmp_path / "exec-id.pdf"
    import re
    import zlib

    pdf_bytes = render_pdf_report(stats, recs, pdf_file, manifest_sha256="a" * 64, hmac_sha256="b" * 64, lang="id")
    assert pdf_file.is_file()
    assert pdf_bytes.startswith(b"%PDF-1.4")
    assert pdf_bytes.rstrip().endswith(b"%%EOF")
    assert b"/Filter /FlateDecode" in pdf_bytes
    assert b"/Count 2" in pdf_bytes
    decompressed = b"\n".join(
        zlib.decompress(m.group(1))
        for m in re.finditer(rb"stream\n(.*?)\nendstream", pdf_bytes, flags=re.DOTALL)
    )
    assert b"Pilar 2 - Audit Header Keamanan OWASP" in decompressed
    assert b"Halaman 1 dari 2" in decompressed


def test_load_test_loopback_remote_guard_and_sla_enforcement(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="allow_remote"):
        run_load_test("https://example.com/api", total_requests=5, concurrency=2)

    def fast_req(url: str, **kw) -> ApiResponse:
        return ApiResponse(200, {"Content-Type": "application/json"}, b'{"ok":true}', 18.5)

    load_dir = tmp_path / "load-out"
    ok_res = run_load_test(
        "http://127.0.0.1:3000/api/items",
        total_requests=12,
        concurrency=4,
        max_p95_ms=500.0,
        output_dir=load_dir,
        lang="id",
        requester=fast_req,
    )
    assert ok_res["passed"] is True
    assert ok_res["total_requests"] == 12
    assert ok_res["error_count"] == 0
    assert (load_dir / "qa-executive-report.pdf").is_file()

    def slow_err_req(url: str, **kw) -> ApiResponse:
        return ApiResponse(503, {}, b"overloaded", 950.0, error="HTTP 503")

    fail_res = run_load_test(
        "https://staging.client.test/api",
        allow_remote=True,
        total_requests=6,
        concurrency=2,
        max_p95_ms=200.0,
        max_error_rate_pct=0.0,
        requester=slow_err_req,
    )
    assert fail_res["passed"] is False
    assert fail_res["error_rate_pct"] == 100.0


def test_hmac_sha256_signed_manifest_and_tamper_rejection(tmp_path: Path) -> None:
    rec = EvidenceRecord("t1", "PASS", utc_now(), "http://127.0.0.1:3000", {"elapsed_ms": 10.0})
    m_path = tmp_path / "signed.json"
    write_manifest([rec], m_path, signing_key="super-secret-hmac-key")
    raw = json.loads(m_path.read_text(encoding="utf-8"))
    assert "hmac_sha256" in raw

    assert verify_manifest(m_path, signing_key="super-secret-hmac-key", require_signature=True) is True
    assert verify_manifest(m_path, signing_key="wrong-hmac-key", require_signature=True) is False

    # Unsigned manifest rejected when require_signature=True
    u_path = tmp_path / "unsigned.json"
    write_manifest([rec], u_path)
    assert verify_manifest(u_path) is True
    assert verify_manifest(u_path, signing_key="super-secret-hmac-key", require_signature=True) is False


def test_full_indonesian_translation_and_spa_seeded_crawler(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert "Pilar 1" in translate_case_name("Pillar 1 — TLS/SSL Protocol & Certificate Expiry Audit", "id")
    assert "dikirim bersamaan" in translate_finding_or_reason(
        "Both Content-Security-Policy and Content-Security-Policy-Report-Only are sent simultaneously",
        "id",
    )

    # SPA shell has ZERO links in initial static HTML, but Pillar 8 renders '/layanan' link via JS!
    spa_shell = '<!doctype html><html lang="id"><head><title>SPA</title><meta name="viewport" content="width=device-width, initial-scale=1"/><meta name="description" content="d"/><link rel="canonical" href="https://spa.test/"/><meta property="og:title" content="t"/><meta property="og:description" content="d"/></head><body><main><div id="root"><h1>App</h1></div></main></body></html>'
    subpage = '<!doctype html><html lang="id"><head><title>Layanan</title><meta name="viewport" content="width=device-width, initial-scale=1"/><meta name="description" content="layanan"/></head><body><main><h1>Layanan Kami</h1></main></body></html>'

    from saqa import spa_audit

    monkeypatch.setattr(
        spa_audit,
        "inspect_spa_runtime",
        lambda url, **kw: {
            "engine": "playwright-chromium",
            "available": True,
            "wall_ms": 100.0,
            "rendered_html": '<!doctype html><html lang="id"><head><title>SPA</title></head><body><main><h1>App</h1><a href="/layanan">Layanan</a></main></body></html>',
            "dom_node_count": 15,
            "console_errors": [],
            "page_errors": [],
            "failed_requests": [],
            "navigation_timing": {},
            "web_vitals": {"fcp_ms": 80, "lcp_ms": 150, "cls": 0.0},
            "asset_budget": {},
        },
    )

    def req(url: str, **kw) -> ApiResponse:
        if url.endswith("/layanan"):
            return ApiResponse(200, {"Content-Type": "text/html"}, subpage.encode("utf-8"), 15.0)
        if url.endswith(("/.env", "/.git/HEAD", "/robots.txt", "/sitemap.xml", "/manifest.webmanifest")):
            return ApiResponse(404, {}, b"", 8.0)
        return ApiResponse(
            200,
            {"Content-Type": "text/html", "Strict-Transport-Security": "max-age=31536000", "X-Content-Type-Options": "nosniff", "Cache-Control": "max-age=60"},
            spa_shell.encode("utf-8"),
            20.0,
        )

    res = run_deep_web_audit(
        "http://spa.test/",
        output_dir=tmp_path / "spa-crawl",
        perf_samples=1,
        include_spa_audit=True,
        crawl_max_pages=3,
        lang="id",
        requester=req,
    )
    by_id = {r.test_id: r for r in res.records}
    crawl_rec = by_id["multi-page.site-crawl-audit"]
    assert crawl_rec.status == "PASS"
    assert len(crawl_rec.details["pages"]) == 1
    assert crawl_rec.details["pages"][0]["url"].endswith("/layanan")
    assert (tmp_path / "spa-crawl" / "qa-executive-report.pdf").is_file()

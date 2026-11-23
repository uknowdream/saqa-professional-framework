"""Unit tests for the 7-pillar automated deep website QA auditor (saqa.web_audit)."""
from __future__ import annotations

import pytest

from saqa.api import ApiResponse
from saqa.evidence import verify_manifest
from saqa.web_audit import run_deep_web_audit

CLEAN_HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="description" content="Enterprise QA site" />
    <meta property="og:title" content="Example QA" />
    <meta property="og:description" content="Example QA description" />
    <link rel="canonical" href="https://example.test/" />
    <link rel="stylesheet" href="/app.css" />
    <script type="application/ld+json">{"@context":"https://schema.org","@type":"WebSite","name":"Example"}</script>
    <title>Example QA Site</title>
  </head>
  <body>
    <header><nav><a href="/about">About</a></nav></header>
    <main>
      <h1>Welcome</h1>
      <h2>Overview</h2>
      <img src="/hero.png" alt="Hero banner" />
      <form>
        <label for="email">Email</label>
        <input id="email" type="email" />
        <button type="submit">Send</button>
      </form>
    </main>
  </body>
</html>
"""

CLEAN_HEADERS = {
    "Content-Type": "text/html; charset=utf-8",
    "Strict-Transport-Security": "max-age=31536000",
    "Content-Security-Policy": "default-src 'self'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Cache-Control": "public, max-age=300",
}


def test_run_deep_web_audit_all_7_pillars_pass_and_write_artifacts(tmp_path):
    def fake_req(url, **kwargs):
        if url.endswith(("/.env", "/.git/HEAD")):
            return ApiResponse(404, {"Content-Type": "text/plain"}, b"Not Found", 12.0)
        if url.endswith("/manifest.webmanifest"):
            return ApiResponse(200, {"Content-Type": "application/json"}, b'{"name":"Example"}', 18.0)
        if url.endswith(("/robots.txt", "/sitemap.xml", "/app.css", "/hero.png", "/about")):
            return ApiResponse(200, {"Content-Type": "text/plain"}, b"ok", 22.0)
        return ApiResponse(200, CLEAN_HEADERS, CLEAN_HTML.encode("utf-8"), 45.0)

    def fake_tls(host, port, *, timeout=10.0):
        return {
            "hostname": host,
            "port": port,
            "protocol": "TLSv1.3",
            "cipher": "TLS_AES_256_GCM_SHA384",
            "issuer": "CN=Test CA",
            "subject": f"CN={host}",
            "san_count": 2,
            "expires_at": "2027-06-01T00:00:00+00:00",
            "days_remaining": 180,
        }

    out_dir = tmp_path / "deep-out"
    result = run_deep_web_audit(
        "https://example.test/",
        output_dir=out_dir,
        perf_samples=2,
        requester=fake_req,
        tls_inspector=fake_tls,
    )
    assert result.passed is True
    assert len(result.records) == 7
    assert result.manifest_path is not None and verify_manifest(result.manifest_path)
    for fname in ("evidence-manifest.json", "suite-summary.json", "report.html", "report.md", "qa-scorecard.png", "qa-analytics-chart.svg", "qa-test-matrix.csv"):
        assert (out_dir / fname).is_file()


def test_run_deep_web_audit_detects_a11y_broken_links_exposed_env_and_expiring_tls():
    bad_html = """<html><head>
      <meta name="viewport" content="width=device-width, user-scalable=no" />
      <script type="application/ld+json">{invalid-json</script>
    </head><body>
      <img src="http://example.test/insecure.png" />
      <button></button>
      <input id="orphan" type="text" />
      <a href="/broken-page">Broken</a>
    </body></html>"""

    def fake_req(url, **kwargs):
        if url.endswith("/.env"):
            return ApiResponse(200, {"Content-Type": "text/plain"}, b"DB_PASSWORD=supersecret", 10.0)
        if url.endswith("/.git/HEAD"):
            return ApiResponse(404, {}, b"", 10.0)
        if url.endswith("/broken-page"):
            return ApiResponse(404, {}, b"not found", 15.0)
        return ApiResponse(200, {"Content-Type": "text/html", "X-Content-Type-Options": "wrong"}, bad_html.encode("utf-8"), 30.0)

    def expiring_tls(host, port, *, timeout=10.0):
        return {
            "hostname": host,
            "port": port,
            "protocol": "TLSv1.2",
            "cipher": "AES",
            "issuer": "CN=Test",
            "subject": f"CN={host}",
            "san_count": 1,
            "expires_at": "2026-11-26T00:00:00+00:00",
            "days_remaining": 2,
        }

    result = run_deep_web_audit(
        "https://example.test/",
        perf_samples=1,
        requester=fake_req,
        tls_inspector=expiring_tls,
    )
    assert result.passed is False
    by_id = {r.test_id: r.status for r in result.records}
    assert by_id["pillar-1.tls-certificate-audit"] == "FAIL"
    assert by_id["pillar-2.security-headers-and-cookies"] == "FAIL"
    assert by_id["pillar-3.dom-wcag-accessibility"] == "FAIL"
    assert by_id["pillar-4.seo-and-structured-data"] == "FAIL"
    assert by_id["pillar-5.broken-links-and-assets"] == "FAIL"
    assert by_id["pillar-6.sensitive-exposure-hygiene"] == "FAIL"


def test_run_deep_web_audit_rejects_invalid_and_credentialed_urls():
    with pytest.raises(ValueError, match="valid http/https"):
        run_deep_web_audit("ftp://example.test")
    with pytest.raises(ValueError, match="embedded credentials"):
        run_deep_web_audit("https://user:pass@example.test/")

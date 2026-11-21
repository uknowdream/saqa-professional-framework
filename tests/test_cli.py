"""Unit and end-to-end integration tests for the SAQA CLI command center."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from saqa import __version__
from saqa.cli import main
from saqa.evidence import EvidenceRecord, utc_now, write_manifest


class _DemoHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path.startswith("/health"):
            body = json.dumps({"status": "ok", "items": [{"id": 1, "name": "widget"}]}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):  # noqa: A002
        return


def test_cli_version_doctor_and_targets(capsys):
    assert main(["version"]) == 0
    assert __version__ in capsys.readouterr().out

    assert main(["doctor", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["framework_version"] == __version__
    assert doc["ready"] is True

    assert main(["doctor"]) == 0
    assert "SAQA Doctor" in capsys.readouterr().out

    assert main(["targets"]) == 0
    text_out = capsys.readouterr().out
    assert "owasp-juice-shop" in text_out
    assert "owasp-webgoat" in text_out

    assert main(["targets", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    names = {item["name"] for item in payload}
    assert {"owasp-juice-shop", "owasp-webgoat"}.issubset(names)


def test_cli_verify_manifest_valid_and_invalid(tmp_path, capsys):
    manifest = tmp_path / "manifest.json"
    record = EvidenceRecord(
        test_id="cli-test-1",
        status="PASS",
        observed_at=utc_now(),
        target="http://127.0.0.1:3000",
        details={"ok": True, "elapsed_ms": 12.0},
    )
    write_manifest([record], manifest)

    assert main(["verify-manifest", str(manifest)]) == 0
    assert "MANIFEST_VALID" in capsys.readouterr().out

    manifest.write_text('{"records": [], "sha256": "invalid"}', encoding="utf-8")
    assert main(["verify-manifest", str(manifest)]) == 1
    assert "MANIFEST_INVALID" in capsys.readouterr().err


def test_cli_init_run_analyze_diff_and_report_end_to_end(tmp_path, capsys):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _DemoHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        # 1. init-suite
        starter_path = tmp_path / "starter.json"
        assert main(["init-suite", str(starter_path), "--base-url", f"http://127.0.0.1:{port}"]) == 0
        assert starter_path.is_file()

        # 2. run-suite against live local loopback server
        suite_path = tmp_path / "live-suite.json"
        suite_path.write_text(
            json.dumps(
                {
                    "name": "live-loopback-smoke",
                    "base_url": f"http://127.0.0.1:{port}",
                    "cases": [
                        {
                            "id": "health-endpoint",
                            "path": "/health",
                            "expect": {
                                "status": 200,
                                "max_ms": 2000,
                                "json_paths": [
                                    {"path": "status", "equals": "ok"},
                                    {"path": "items[0].id", "type": "integer", "min": 1},
                                ],
                            },
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        run1_dir = tmp_path / "run1"
        html_out = tmp_path / "report.html"
        md_out = tmp_path / "report.md"
        history_path = tmp_path / "history.jsonl"

        exit_code = main(
            [
                "run-suite",
                str(suite_path),
                "--output-dir",
                str(run1_dir),
                "--html",
                str(html_out),
                "--md",
                str(md_out),
                "--history",
                str(history_path),
                "--commit-sha",
                "commit-001",
            ]
        )
        assert exit_code == 0
        assert html_out.is_file() and "SAQA Report" in html_out.read_text(encoding="utf-8")
        assert md_out.is_file() and "# SAQA Report" in md_out.read_text(encoding="utf-8")
        assert history_path.is_file()

        # 3. analyze manifest and history
        manifest_path = run1_dir / "evidence-manifest.json"
        capsys.readouterr()
        assert main(["analyze", str(manifest_path), "--json"]) == 0
        stats = json.loads(capsys.readouterr().out)
        assert stats["overall_status"] == "PASS"
        assert stats["health_grade"] == "A"

        assert main(["analyze", str(history_path), "--json"]) == 0
        hist = json.loads(capsys.readouterr().out)
        assert hist["commit_count"] == 1

        # 4. diff manifests
        assert main(["diff", str(manifest_path), str(manifest_path), "--json"]) == 0
        diff_data = json.loads(capsys.readouterr().out)
        assert diff_data["verdict"] == "STABLE"

        # 5. standalone report command
        html2 = tmp_path / "report2.html"
        assert main(["report", str(manifest_path), "--html", str(html2), "--history", str(history_path)]) == 0
        assert html2.is_file()
    finally:
        server.shutdown()
        server.server_close()


def test_cli_generate_data_all_modes(tmp_path, capsys):
    for args in (
        ["generate-data", "bva", "--min", "1", "--max", "10"],
        ["generate-data", "bva-str", "--min", "2", "--max", "8"],
        ["generate-data", "pairwise", "--seed", "7"],
        ["generate-data", "users", "--count", "2", "--seed", "7"],
        ["generate-data", "invoices", "--count", "2", "--seed", "7"],
        ["generate-data", "edge-cases", "--category", "dates"],
    ):
        assert main(args) == 0
        parsed = json.loads(capsys.readouterr().out)
        assert parsed

    out_file = tmp_path / "pairwise.json"
    assert main(["generate-data", "pairwise", "--output", str(out_file)]) == 0
    saved = json.loads(out_file.read_text(encoding="utf-8"))
    assert saved["coverage"]["coverage_pct"] == 100.0

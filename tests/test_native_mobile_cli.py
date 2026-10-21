import json

from scripts.validate_native_mobile_evidence import main
from saqa.native_mobile import SCHEMA


def valid_payload():
    return {
        "schema": SCHEMA, "platform": "android", "package_id": "com.example.app",
        "app_sha256": "b" * 64, "test_run_id": "android-emulator-42",
        "executed_at": "2026-10-21T12:00:00Z",
        "device": {"os_version": "Android 15", "model": "Pixel_8_API_35", "runtime": "emulator"},
        "tests": [{"test_id": "launch", "status": "PASS"}],
    }


def test_cli_writes_normalized_evidence(tmp_path):
    source, output = tmp_path / "input.json", tmp_path / "out" / "normalized.json"
    source.write_text(json.dumps(valid_payload()), encoding="utf-8")
    assert main(["--input", str(source), "--output", str(output)]) == 0
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["status"] == "PASS"
    assert result["app_sha256"] == "b" * 64


def test_cli_returns_unverified_for_bad_evidence(tmp_path):
    source, output = tmp_path / "bad.json", tmp_path / "out.json"
    source.write_text("[]", encoding="utf-8")
    assert main(["--input", str(source), "--output", str(output)]) == 2
    assert not output.exists()


def test_cli_returns_fail_for_failed_native_test(tmp_path):
    source, output = tmp_path / "input.json", tmp_path / "out.json"
    payload = valid_payload()
    payload["tests"][0]["status"] = "FAIL"
    source.write_text(json.dumps(payload), encoding="utf-8")
    assert main(["--input", str(source), "--output", str(output)]) == 1


def test_cli_removes_stale_pass_artifact_before_invalid_input(tmp_path):
    source, output = tmp_path / "bad.json", tmp_path / "out.json"
    source.write_text("[]", encoding="utf-8")
    output.write_text(json.dumps({"status": "PASS", "app_sha256": "old"}), encoding="utf-8")
    assert main(["--input", str(source), "--output", str(output)]) == 2
    assert not output.exists()

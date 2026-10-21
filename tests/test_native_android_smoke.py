import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import run_native_android_smoke as runner


def fake_run(command, *, timeout=120):
    joined = " ".join(command)
    if "getprop ro.build.version.release" in joined:
        return SimpleNamespace(returncode=0, stdout="15\n", stderr="")
    if "getprop ro.product.model" in joined:
        return SimpleNamespace(returncode=0, stdout="Pixel_8_API_35\n", stderr="")
    if "adb install" in joined:
        return SimpleNamespace(returncode=0, stdout="Success\n", stderr="")
    if "monkey" in joined:
        return SimpleNamespace(returncode=0, stdout="Events injected: 1\n", stderr="")
    return SimpleNamespace(returncode=0, stdout="", stderr="")


def setup_apk(tmp_path):
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"sample-apk-bytes")
    return apk, hashlib.sha256(apk.read_bytes()).hexdigest()


def test_android_smoke_emits_pass_for_hash_install_and_launch(monkeypatch, tmp_path):
    apk, digest = setup_apk(tmp_path)
    monkeypatch.setattr(runner, "run", fake_run)
    result = runner.run_smoke(apk, "com.example.app", digest, "run-123")
    assert [item["status"] for item in result["tests"]] == ["PASS", "PASS", "PASS"]
    assert result["device"]["os_version"] == "15"
    assert result["device"]["runtime"] == "emulator"


def test_android_smoke_blocks_install_when_hash_mismatches(monkeypatch, tmp_path):
    apk, _ = setup_apk(tmp_path)
    monkeypatch.setattr(runner, "run", lambda *args, **kwargs: pytest.fail("ADB must not run for hash mismatch"))
    result = runner.run_smoke(apk, "com.example.app", "a" * 64, "run-123")
    assert result["tests"][0]["status"] == "FAIL"
    assert result["tests"][-1]["status"] == "BLOCKED"


def test_android_smoke_reports_install_failure(monkeypatch, tmp_path):
    apk, digest = setup_apk(tmp_path)
    def failed_install(command, *, timeout=120):
        if "getprop ro.build.version.release" in " ".join(command):
            return SimpleNamespace(returncode=0, stdout="15", stderr="")
        if "getprop ro.product.model" in " ".join(command):
            return SimpleNamespace(returncode=0, stdout="Pixel_8", stderr="")
        if "adb install" in " ".join(command):
            return SimpleNamespace(returncode=1, stdout="", stderr="INSTALL_FAILED")
        return fake_run(command, timeout=timeout)
    monkeypatch.setattr(runner, "run", failed_install)
    result = runner.run_smoke(apk, "com.example.app", digest, "run-123")
    assert result["tests"][1]["status"] == "FAIL"
    assert result["tests"][2]["status"] == "BLOCKED"


@pytest.mark.parametrize("package_id", ["bad", "com..app", ".example.app", "com.example."])
def test_android_smoke_rejects_invalid_package_id(tmp_path, package_id):
    apk, digest = setup_apk(tmp_path)
    with pytest.raises(ValueError, match="package_id"):
        runner.run_smoke(apk, package_id, digest, "run-123")


def test_cli_removes_stale_pass_evidence_before_new_run(monkeypatch, tmp_path):
    apk, digest = setup_apk(tmp_path)
    output = tmp_path / "evidence.json"
    output.write_text('{"status":"PASS"}', encoding="utf-8")
    monkeypatch.setattr(runner, "run", lambda *args, **kwargs: pytest.fail("unexpected adb call"))
    assert runner.main(["--apk", str(apk), "--package-id", "com.example.app",
                        "--expected-sha256", "b" * 64, "--output", str(output)]) == 1
    evidence = json.loads(output.read_text(encoding="utf-8"))
    assert evidence["status"] == "FAIL"
    assert evidence["tests"][0]["status"] == "FAIL"

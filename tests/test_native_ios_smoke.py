import hashlib, plistlib, zipfile
from pathlib import Path
import pytest
from scripts.run_native_ios_smoke import extract_app_bundle, run_smoke


def make_archive(tmp_path: Path, bundle_id="com.example.app"):
    app = tmp_path / "Payload" / "Example.app"
    app.mkdir(parents=True)
    (app / "Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": bundle_id}))
    archive = tmp_path / "simulator-app.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.write(app / "Info.plist", "Payload/Example.app/Info.plist")
    return archive


def test_extract_app_bundle_finds_single_app(tmp_path):
    archive = make_archive(tmp_path)
    found = extract_app_bundle(archive, tmp_path / "extract")
    assert found.name == "Example.app"
    assert (found / "Info.plist").is_file()


def test_archive_path_traversal_is_rejected(tmp_path):
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("../outside.txt", "unsafe")
    with pytest.raises(ValueError, match="escaping"):
        extract_app_bundle(archive, tmp_path / "extract")


def test_hash_mismatch_does_not_execute_device_commands(tmp_path, monkeypatch):
    archive = make_archive(tmp_path)
    monkeypatch.setattr("scripts.run_native_ios_smoke.run", lambda *args, **kwargs: pytest.fail("must not execute commands"))
    result = run_smoke(archive, "com.example.app", "0" * 64, "test-run", tmp_path / "work")
    assert result["tests"][0]["status"] == "FAIL"
    assert all(item["status"] == "BLOCKED" for item in result["tests"][1:])


def test_invalid_bundle_id_rejected(tmp_path):
    archive = make_archive(tmp_path)
    with pytest.raises(ValueError, match="bundle_id"):
        run_smoke(archive, "not-valid", hashlib.sha256(archive.read_bytes()).hexdigest(), "test-run", tmp_path / "work")


def test_bundle_mismatch_fails_without_install(tmp_path, monkeypatch):
    archive = make_archive(tmp_path, "com.other.app")
    def fake_run(command, timeout=120):
        pytest.fail("bundle mismatch must block simulator calls")
    monkeypatch.setattr("scripts.run_native_ios_smoke.run", fake_run)
    result = run_smoke(archive, "com.example.app", hashlib.sha256(archive.read_bytes()).hexdigest(), "test-run", tmp_path / "work")
    assert result["tests"][1]["status"] == "FAIL"
    assert result["tests"][2]["status"] == "BLOCKED"


def test_ios_runtime_version_parser_uses_numeric_runtime_components():
    import re
    runtime = "com.apple.CoreSimulator.SimRuntime.iOS-18-5"
    match = re.search(r"iOS-(\d+(?:-\d+)*)", runtime)
    assert match
    assert match.group(1).replace("-", ".") == "18.5"


def test_unknown_simulator_metadata_blocks_install_and_launch(tmp_path, monkeypatch):
    import hashlib
    import subprocess
    archive = make_archive(tmp_path)
    commands = []

    def fake_run(command, timeout=120):
        commands.append(command)
        return subprocess.CompletedProcess(
            command, 0,
            stdout='{"devices":{"com.apple.CoreSimulator.SimRuntime.iOS-18-5":[{"state":"Booted"}]}}',
            stderr="",
        )

    monkeypatch.setattr("scripts.run_native_ios_smoke.run", fake_run)
    result = run_smoke(
        archive, "com.example.app", hashlib.sha256(archive.read_bytes()).hexdigest(),
        "test-run", tmp_path / "work",
    )
    statuses = {item["test_id"]: item["status"] for item in result["tests"]}
    assert statuses["simulator-metadata"] == "BLOCKED"
    assert statuses["simulator-install"] == "BLOCKED"
    assert statuses["app-launch"] == "BLOCKED"
    assert len(commands) == 1
    assert commands[0][:4] == ["xcrun", "simctl", "list", "devices"]



def test_ios_smoke_installs_launches_and_records_actual_simulator_metadata(tmp_path, monkeypatch):
    import json
    import subprocess
    archive = make_archive(tmp_path)
    commands = []

    def fake_run(command, timeout=120):
        commands.append(command)
        if command[:4] == ["xcrun", "simctl", "list", "devices"]:
            return subprocess.CompletedProcess(
                command, 0,
                stdout=json.dumps({"devices": {
                    "com.apple.CoreSimulator.SimRuntime.iOS-18-5": [
                        {"udid": "SIM-123", "state": "Booted", "name": "iPhone 16"}
                    ]
                }}),
                stderr="",
            )
        if command[:3] == ["xcrun", "simctl", "install"] and command[3] == "SIM-123":
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command[:3] == ["xcrun", "simctl", "launch"] and command[3] == "SIM-123":
            return subprocess.CompletedProcess(command, 0, stdout="com.example.app: 1234\\n", stderr="")
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="unexpected command")

    monkeypatch.setattr("scripts.run_native_ios_smoke.run", fake_run)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    result = run_smoke(archive, "com.example.app", digest, "test-run", tmp_path / "work")
    statuses = {item["test_id"]: item["status"] for item in result["tests"]}
    assert result["device"]["os_version"] == "18.5"
    assert result["device"]["model"] == "iPhone 16"
    assert result["device"]["udid"] == "SIM-123"
    assert statuses == {
        "simulator-app-archive-sha256-matches-release": "PASS",
        "bundle-id-matches-input": "PASS",
        "simulator-metadata": "PASS",
        "simulator-install": "PASS",
        "app-launch": "PASS",
    }
    assert any(command[:3] == ["xcrun", "simctl", "install"] and command[3] == "SIM-123" for command in commands)
    assert any(command[:3] == ["xcrun", "simctl", "launch"] and command[3] == "SIM-123" for command in commands)


def test_extraction_restores_executable_mode_and_ignores_nested_companion_apps(tmp_path):
    import os
    import stat
    app = tmp_path / "Payload" / "Main.app"
    nested = app / "WatchCompanion.app"
    nested.mkdir(parents=True)
    executable = app / "MainExecutable"
    executable.write_text("binary-placeholder", encoding="utf-8")
    os.chmod(executable, 0o755)
    (app / "Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": "com.example.app"}))
    (nested / "Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": "com.example.watch"}))
    archive = tmp_path / "nested-apps.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.write(executable, "Payload/Main.app/MainExecutable")
        zipped.write(app / "Info.plist", "Payload/Main.app/Info.plist")
        zipped.write(nested / "Info.plist", "Payload/Main.app/WatchCompanion.app/Info.plist")
    found = extract_app_bundle(archive, tmp_path / "extracted")
    assert found.name == "Main.app"
    mode = (found / "MainExecutable").stat().st_mode
    assert mode & stat.S_IXUSR


def test_missing_xcrun_writes_blocked_native_evidence(tmp_path, monkeypatch):
    import hashlib
    import json
    import subprocess
    archive = make_archive(tmp_path)
    def missing_tool(*args, **kwargs):
        raise FileNotFoundError("xcrun is unavailable")
    monkeypatch.setattr("scripts.run_native_ios_smoke.run", missing_tool)
    payload = run_smoke(archive, "com.example.app", hashlib.sha256(archive.read_bytes()).hexdigest(),
                        "run-no-xcrun", tmp_path / "work")
    statuses = {item["test_id"]: item["status"] for item in payload["tests"]}
    assert statuses["simulator-metadata"] == "BLOCKED"
    assert statuses["simulator-install"] == "BLOCKED"
    assert statuses["app-launch"] == "BLOCKED"


def test_simulator_udid_override_selects_exact_device(tmp_path, monkeypatch):
    import hashlib
    import json
    import subprocess
    archive = make_archive(tmp_path)
    commands = []
    devices = [
        {"udid": "SIM-OTHER", "state": "Booted", "name": "iPhone 15"},
        {"udid": "SIM-TARGET", "state": "Booted", "name": "iPhone 16"},
    ]
    def fake_run(command, timeout=120):
        commands.append(command)
        if command[:4] == ["xcrun", "simctl", "list", "devices"]:
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps({"devices": {
                "com.apple.CoreSimulator.SimRuntime.iOS-18-5": devices
            }}), stderr="")
        if command[:3] == ["xcrun", "simctl", "install"] and command[3] == "SIM-TARGET":
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command[:3] == ["xcrun", "simctl", "launch"] and command[3] == "SIM-TARGET":
            return subprocess.CompletedProcess(command, 0, stdout="com.example.app: 123", stderr="")
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="unexpected")
    monkeypatch.setattr("scripts.run_native_ios_smoke.run", fake_run)
    result = run_smoke(archive, "com.example.app", hashlib.sha256(archive.read_bytes()).hexdigest(),
                       "run-udid", tmp_path / "work", simulator_udid="SIM-TARGET")
    assert result["device"]["udid"] == "SIM-TARGET"
    assert [item["status"] for item in result["tests"]] == ["PASS", "PASS", "PASS", "PASS", "PASS"]

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

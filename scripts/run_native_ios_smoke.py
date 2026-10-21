"""Install and launch an authorized iOS Simulator .app bundle from a verified ZIP."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import re
import shutil
import stat
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

SHA256 = re.compile(r"^[0-9a-f]{64}$")
BUNDLE_ID = re.compile(r"^[A-Za-z][A-Za-z0-9-]*(\.[A-Za-z][A-Za-z0-9-]*)+$")


def run(command: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _test(test_id: str, status: str, details: str | None = None) -> dict[str, str]:
    item = {"test_id": test_id, "status": status}
    if details:
        item["details"] = details[:400]
    return item


def _blocked_simulator_steps(tests: list[dict[str, str]], reason: str) -> None:
    tests.extend([
        _test("simulator-metadata", "BLOCKED", reason),
        _test("simulator-install", "BLOCKED", "installation skipped because simulator identity is unverified"),
        _test("app-launch", "BLOCKED", "launch skipped because simulator identity is unverified"),
    ])


def extract_app_bundle(archive: Path, destination: Path) -> Path:
    """Safely extract a simulator ZIP and restore archived executable mode bits."""
    root = destination.resolve()
    root.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        for member in members:
            posix_path = PurePosixPath(member.filename)
            if posix_path.is_absolute() or ".." in posix_path.parts:
                raise ValueError("archive contains a path escaping the extraction directory")
            target = (root / member.filename).resolve()
            if not target.is_relative_to(root):
                raise ValueError("archive contains a path escaping the extraction directory")
            member_mode = (member.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(member_mode):
                raise ValueError("archive contains a symbolic link, which is not allowed")
        bundle.extractall(root)
        for member in members:
            mode = (member.external_attr >> 16) & 0o777
            if not mode:
                continue
            target = (root / member.filename).resolve()
            if target.is_relative_to(root) and target.exists():
                os.chmod(target, mode)

    apps = [
        path for path in root.rglob("*.app")
        if path.is_dir() and (
            path.parent == root or (path.parent.name == "Payload" and path.parent.parent == root)
        )
    ]
    if len(apps) != 1:
        raise ValueError(f"expected exactly one top-level .app bundle in simulator archive; found {len(apps)}")
    return apps[0]


def run_smoke(
    archive: Path,
    bundle_id: str,
    expected_sha256: str,
    run_id: str,
    workdir: Path,
    simulator_udid: str | None = None,
) -> dict[str, Any]:
    if not isinstance(bundle_id, str) or not BUNDLE_ID.fullmatch(bundle_id):
        raise ValueError("bundle_id must be a valid reverse-domain iOS bundle identifier")
    if not isinstance(expected_sha256, str) or not SHA256.fullmatch(expected_sha256):
        raise ValueError("expected_sha256 must be a lowercase SHA-256 digest")
    if not archive.is_file():
        raise ValueError(f"simulator app archive does not exist: {archive}")
    actual = file_sha256(archive)
    tests = [_test("simulator-app-archive-sha256-matches-release", "PASS" if actual == expected_sha256 else "FAIL")]
    device = {"os_version": "unavailable", "model": "unavailable", "runtime": "simulator"}

    if actual != expected_sha256:
        tests.extend([
            _test("bundle-id-matches-input", "BLOCKED", "archive digest mismatch prevented bundle inspection"),
            _test("simulator-metadata", "BLOCKED", "archive digest mismatch prevented simulator use"),
            _test("simulator-install", "BLOCKED", "archive digest mismatch prevented installation"),
            _test("app-launch", "BLOCKED", "archive digest mismatch prevented launch"),
        ])
    else:
        app = extract_app_bundle(archive, workdir / "extracted")
        try:
            info = plistlib.loads((app / "Info.plist").read_bytes())
        except (OSError, plistlib.InvalidFileException, ValueError) as exc:
            raise ValueError(f"cannot read simulator app Info.plist: {exc}") from exc
        actual_bundle = info.get("CFBundleIdentifier")
        if actual_bundle != bundle_id:
            tests.extend([
                _test("bundle-id-matches-input", "FAIL", "app bundle ID does not match the requested identifier"),
                _test("simulator-metadata", "BLOCKED", "bundle ID mismatch prevented simulator use"),
                _test("simulator-install", "BLOCKED", "bundle ID mismatch prevented installation"),
                _test("app-launch", "BLOCKED", "bundle ID mismatch prevented launch"),
            ])
        else:
            tests.append(_test("bundle-id-matches-input", "PASS"))
            try:
                listing = run(["xcrun", "simctl", "list", "devices", "available", "-j"], timeout=60)
            except (OSError, subprocess.TimeoutExpired) as exc:
                _blocked_simulator_steps(tests, f"simulator inventory could not be read: {type(exc).__name__}: {exc}")
            else:
                inventory: Any = None
                if listing.returncode == 0:
                    try:
                        inventory = json.loads(listing.stdout)
                    except (json.JSONDecodeError, TypeError):
                        inventory = None
                devices_by_runtime = inventory.get("devices") if isinstance(inventory, dict) else None
                if listing.returncode != 0 or not isinstance(devices_by_runtime, dict):
                    _blocked_simulator_steps(tests, "simulator inventory command failed or returned invalid JSON")
                else:
                    selected = None
                    runtime_name = ""
                    wanted_udid = simulator_udid.strip() if isinstance(simulator_udid, str) and simulator_udid.strip() else None
                    for runtime, devices in devices_by_runtime.items():
                        if "iOS" not in runtime or not isinstance(devices, list):
                            continue
                        for item in devices:
                            if not isinstance(item, dict) or item.get("state") != "Booted":
                                continue
                            if wanted_udid and item.get("udid") != wanted_udid:
                                continue
                            selected = item
                            runtime_name = runtime
                            break
                        if selected:
                            break
                    model = selected.get("name") if selected else None
                    udid = selected.get("udid") if selected else None
                    runtime_match = re.search(r"iOS-(\d+(?:-\d+)*)", runtime_name)
                    os_version = runtime_match.group(1).replace("-", ".") if runtime_match else None
                    if not isinstance(model, str) or not model.strip() or not isinstance(udid, str) or not udid.strip() or not os_version:
                        _blocked_simulator_steps(tests, "no matching booted iOS simulator has valid UDID, model, and runtime metadata")
                    else:
                        device.update({"model": model.strip(), "os_version": os_version, "udid": udid.strip()})
                        tests.append(_test("simulator-metadata", "PASS"))
                        try:
                            install = run(["xcrun", "simctl", "install", udid, str(app)], timeout=180)
                        except (OSError, subprocess.TimeoutExpired) as exc:
                            tests.append(_test("simulator-install", "BLOCKED", f"install outcome could not be verified: {type(exc).__name__}: {exc}"))
                            tests.append(_test("app-launch", "BLOCKED", "launch skipped because installation outcome is unverified"))
                        else:
                            installed = install.returncode == 0
                            tests.append(_test("simulator-install", "PASS" if installed else "FAIL",
                                               None if installed else "simctl install returned failure"))
                            if not installed:
                                tests.append(_test("app-launch", "BLOCKED", "launch skipped because app installation failed"))
                            else:
                                try:
                                    launch = run(["xcrun", "simctl", "launch", udid, bundle_id], timeout=60)
                                except (OSError, subprocess.TimeoutExpired) as exc:
                                    tests.append(_test("app-launch", "BLOCKED", f"launch outcome could not be verified: {type(exc).__name__}: {exc}"))
                                else:
                                    launched = launch.returncode == 0 and bundle_id in (launch.stdout or "")
                                    tests.append(_test("app-launch", "PASS" if launched else "FAIL",
                                                       None if launched else "simctl launch did not confirm the requested bundle ID"))

    return {
        "schema": "saqa.native-mobile-evidence.v1",
        "platform": "ios",
        "bundle_id": bundle_id,
        "app_sha256": actual,
        "test_run_id": run_id,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "device": device,
        "tests": tests,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-archive", required=True, type=Path, help="ZIP containing an iOS Simulator .app bundle")
    parser.add_argument("--bundle-id", required=True)
    parser.add_argument("--expected-sha256", required=True, help="SHA-256 of the exact simulator ZIP archive")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--simulator-udid", default=os.getenv("SAQA_IOS_SIMULATOR_UDID"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.app_archive.resolve() == args.output.resolve():
        print(json.dumps({"schema": "saqa.native-mobile-evidence.v1", "status": "UNVERIFIED",
                          "error": "app archive and evidence output must be different files"}, indent=2))
        return 2
    try:
        args.output.unlink(missing_ok=True)
        with tempfile.TemporaryDirectory(prefix="saqa-ios-smoke-") as temp:
            payload = run_smoke(args.app_archive, args.bundle_id, args.expected_sha256, args.run_id,
                                Path(temp), simulator_udid=args.simulator_udid)
        from saqa.native_mobile import validate_native_mobile_evidence
        result = validate_native_mobile_evidence(payload)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, ValueError, zipfile.BadZipFile, subprocess.TimeoutExpired) as exc:
        fallback = {"schema": "saqa.native-mobile-evidence.v1", "status": "UNVERIFIED",
                    "platform": "ios", "test_run_id": args.run_id, "error": f"{type(exc).__name__}: {exc}"}
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(fallback, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        except OSError:
            pass
        print(json.dumps(fallback, indent=2))
        return 2
    print(json.dumps({"status": result["status"], "platform": "ios", "test_count": len(result["tests"])}, indent=2))
    return 0 if result["status"] == "PASS" else (1 if result["status"] == "FAIL" else 2)


if __name__ == "__main__":
    raise SystemExit(main())

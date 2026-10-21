"""Run a minimal Android emulator install-and-launch smoke test and emit native evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PACKAGE_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def run(command: list[str], *, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)


def adb_text(command: list[str], *, timeout: int = 30) -> str:
    result = run(["adb", *command], timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(f"adb command failed ({result.returncode}): {' '.join(command)}: {(result.stderr or result.stdout).strip()[:500]}")
    return result.stdout.strip()


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_smoke(apk: Path, package_id: str, expected_sha256: str, run_id: str) -> dict[str, Any]:
    if not PACKAGE_ID.fullmatch(package_id):
        raise ValueError("package_id must be a valid reverse-domain Android application ID")
    if not SHA256.fullmatch(expected_sha256):
        raise ValueError("expected_sha256 must be a lowercase SHA-256 digest")
    if not apk.is_file():
        raise ValueError(f"APK file does not exist: {apk}")
    actual_hash = _hash(apk)
    tests = [{"test_id": "apk-sha256-matches-release", "status": "PASS" if actual_hash == expected_sha256 else "FAIL"}]
    device = {"os_version": "unavailable", "model": "unavailable", "runtime": "emulator"}
    if actual_hash == expected_sha256:
        try:
            device = {
                "os_version": adb_text(["shell", "getprop", "ro.build.version.release"]),
                "model": adb_text(["shell", "getprop", "ro.product.model"]),
                "runtime": "emulator",
            }
            if not device["os_version"] or not device["model"]:
                raise RuntimeError("emulator OS/model metadata is empty")
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
            tests.append({"test_id": "emulator-metadata", "status": "BLOCKED"})
            tests.append({"test_id": "apk-install", "status": "BLOCKED"})
            tests.append({"test_id": "app-launch", "status": "BLOCKED"})
        else:
            install = run(["adb", "install", "-r", str(apk)], timeout=180)
            installed = install.returncode == 0 and "success" in (install.stdout + install.stderr).lower()
            tests.append({"test_id": "apk-install", "status": "PASS" if installed else "FAIL"})
            if installed:
                launch = run(["adb", "shell", "monkey", "-p", package_id, "1"], timeout=60)
                output = (launch.stdout + "\n" + launch.stderr).lower()
                launched = launch.returncode == 0 and "events injected: 1" in output and "no activities found to run" not in output and "monkey aborted" not in output
                tests.append({"test_id": "app-launch", "status": "PASS" if launched else "FAIL"})
            else:
                tests.append({"test_id": "app-launch", "status": "BLOCKED"})
    else:
        tests.extend([
            {"test_id": "emulator-metadata", "status": "BLOCKED"},
            {"test_id": "apk-install", "status": "BLOCKED"},
            {"test_id": "app-launch", "status": "BLOCKED"},
        ])
    return {
        "schema": "saqa.native-mobile-evidence.v1",
        "platform": "android",
        "package_id": package_id,
        "app_sha256": actual_hash,
        "test_run_id": run_id,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "device": device,
        "tests": tests,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apk", required=True, type=Path)
    parser.add_argument("--package-id", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--run-id", default=os.getenv("GITHUB_RUN_ID", "local-android-smoke"))
    args = parser.parse_args(argv)
    args.output.unlink(missing_ok=True)
    try:
        from saqa.native_mobile import validate_native_mobile_evidence
        payload = run_smoke(args.apk, args.package_id, args.expected_sha256, args.run_id)
        result = validate_native_mobile_evidence(payload)
    except (OSError, UnicodeError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"schema": "saqa.native-mobile-evidence.v1", "status": "UNVERIFIED", "error": str(exc)}, indent=2))
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "test_count": result["test_count"], "test_run_id": result["test_run_id"]}, indent=2))
    return 0 if result["status"] == "PASS" else (1 if result["status"] == "FAIL" else 2)


if __name__ == "__main__":
    raise SystemExit(main())

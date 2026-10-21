"""Run an authorized Android emulator install, launch, and liveness smoke test."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import time
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


def _test(test_id: str, status: str, details: str | None = None) -> dict[str, str]:
    item = {"test_id": test_id, "status": status}
    if details:
        item["details"] = details[:400]
    return item


def run_smoke(apk: Path, package_id: str, expected_sha256: str, run_id: str) -> dict[str, Any]:
    if not isinstance(package_id, str) or not PACKAGE_ID.fullmatch(package_id):
        raise ValueError("package_id must be a valid reverse-domain Android application ID")
    if not isinstance(expected_sha256, str) or not SHA256.fullmatch(expected_sha256):
        raise ValueError("expected_sha256 must be a lowercase SHA-256 digest")
    if not apk.is_file():
        raise ValueError(f"APK file does not exist: {apk}")
    actual_hash = _hash(apk)
    tests = [_test("apk-sha256-matches-release", "PASS" if actual_hash == expected_sha256 else "FAIL")]
    device = {"os_version": "unavailable", "model": "unavailable", "runtime": "emulator"}

    if actual_hash != expected_sha256:
        tests.extend([
            _test("emulator-metadata", "BLOCKED", "APK digest mismatch prevented device execution"),
            _test("apk-install", "BLOCKED", "APK digest mismatch prevented installation"),
            _test("app-launch", "BLOCKED", "APK digest mismatch prevented launch"),
        ])
    else:
        try:
            os_version = adb_text(["shell", "getprop", "ro.build.version.release"])
            model = adb_text(["shell", "getprop", "ro.product.model"])
            if not os_version or not model:
                raise RuntimeError("emulator OS/model metadata is empty")
            device = {"os_version": os_version, "model": model, "runtime": "emulator"}
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
            reason = f"emulator metadata unavailable: {type(exc).__name__}: {exc}"
            tests.extend([
                _test("emulator-metadata", "BLOCKED", reason),
                _test("apk-install", "BLOCKED", "installation skipped because emulator metadata is unverified"),
                _test("app-launch", "BLOCKED", "launch skipped because emulator metadata is unverified"),
            ])
        else:
            try:
                install = run(["adb", "install", "-r", str(apk)], timeout=180)
            except (OSError, subprocess.TimeoutExpired) as exc:
                reason = f"ADB install could not be verified: {type(exc).__name__}: {exc}"
                tests.append(_test("apk-install", "BLOCKED", reason))
                tests.append(_test("app-launch", "BLOCKED", "launch skipped because install outcome is unverified"))
            else:
                installed = install.returncode == 0 and "success" in (install.stdout + install.stderr).lower()
                tests.append(_test("apk-install", "PASS" if installed else "FAIL",
                                   None if installed else "ADB install returned failure"))
                if not installed:
                    tests.append(_test("app-launch", "BLOCKED", "launch skipped because APK installation failed"))
                else:
                    try:
                        launch = run(["adb", "shell", "monkey", "-p", package_id, "1"], timeout=60)
                    except (OSError, subprocess.TimeoutExpired) as exc:
                        tests.append(_test("app-launch", "BLOCKED", f"launch outcome could not be verified: {type(exc).__name__}: {exc}"))
                    else:
                        output = (launch.stdout + "\n" + launch.stderr).lower()
                        injected = launch.returncode == 0 and "events injected: 1" in output
                        explicit_failure = "no activities found to run" in output or "monkey aborted" in output
                        if not injected or explicit_failure:
                            tests.append(_test("app-launch", "FAIL", "monkey did not confirm an activity launch"))
                        else:
                            time.sleep(1)
                            try:
                                pid_result = run(["adb", "shell", "pidof", package_id], timeout=30)
                            except (OSError, subprocess.TimeoutExpired) as exc:
                                tests.append(_test("app-launch", "BLOCKED", f"post-launch process could not be verified: {type(exc).__name__}: {exc}"))
                            else:
                                alive = pid_result.returncode == 0 and bool(pid_result.stdout.strip())
                                tests.append(_test("app-launch", "PASS" if alive else "FAIL",
                                                   None if alive else "app process was not present after launch"))

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
    if args.apk.resolve() == args.output.resolve():
        print(json.dumps({"schema": "saqa.native-mobile-evidence.v1", "status": "UNVERIFIED",
                          "error": "APK input and evidence output must be different files"}, indent=2))
        return 2
    try:
        args.output.unlink(missing_ok=True)
        from saqa.native_mobile import validate_native_mobile_evidence
        payload = run_smoke(args.apk, args.package_id, args.expected_sha256, args.run_id)
        result = validate_native_mobile_evidence(payload)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, UnicodeError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        fallback = {"schema": "saqa.native-mobile-evidence.v1", "status": "UNVERIFIED",
                    "platform": "android", "test_run_id": args.run_id, "error": f"{type(exc).__name__}: {exc}"}
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(fallback, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        except OSError:
            pass
        print(json.dumps(fallback, indent=2))
        return 2
    print(json.dumps({"status": result["status"], "test_count": result["test_count"], "test_run_id": result["test_run_id"]}, indent=2))
    return 0 if result["status"] == "PASS" else (1 if result["status"] == "FAIL" else 2)


if __name__ == "__main__":
    raise SystemExit(main())

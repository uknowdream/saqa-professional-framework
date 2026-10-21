"""Install and launch an authorized iOS Simulator .app bundle from a verified zip."""
from __future__ import annotations
import argparse, hashlib, json, os, plistlib, re, shutil, subprocess, tempfile, zipfile
from datetime import datetime, timezone
from pathlib import Path
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


def extract_app_bundle(archive: Path, destination: Path) -> Path:
    root = destination.resolve()
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            target = (root / member.filename).resolve()
            if not target.is_relative_to(root):
                raise ValueError("archive contains a path escaping the extraction directory")
        bundle.extractall(root)
    apps = [path for path in root.rglob("*.app") if path.is_dir()]
    if len(apps) != 1:
        raise ValueError(f"expected exactly one .app bundle in simulator archive; found {len(apps)}")
    return apps[0]


def run_smoke(archive: Path, bundle_id: str, expected_sha256: str, run_id: str, workdir: Path) -> dict[str, Any]:
    if not BUNDLE_ID.fullmatch(bundle_id):
        raise ValueError("bundle_id must be a valid reverse-domain iOS bundle identifier")
    if not SHA256.fullmatch(expected_sha256):
        raise ValueError("expected_sha256 must be a lowercase SHA-256 digest")
    if not archive.is_file():
        raise ValueError(f"simulator app archive does not exist: {archive}")
    actual = file_sha256(archive)
    tests = [{"test_id": "simulator-app-archive-sha256-matches-release", "status": "PASS" if actual == expected_sha256 else "FAIL"}]
    device = {"os_version": "unavailable", "model": "unavailable", "runtime": "simulator"}
    if actual == expected_sha256:
        app = extract_app_bundle(archive, workdir / "extracted")
        try:
            info = plistlib.loads((app / "Info.plist").read_bytes())
        except (OSError, plistlib.InvalidFileException) as exc:
            raise ValueError(f"cannot read simulator app Info.plist: {exc}") from exc
        actual_bundle = info.get("CFBundleIdentifier")
        if actual_bundle != bundle_id:
            tests.append({"test_id": "bundle-id-matches-input", "status": "FAIL"})
            tests.append({"test_id": "simulator-install", "status": "BLOCKED"})
            tests.append({"test_id": "app-launch", "status": "BLOCKED"})
        else:
            tests.append({"test_id": "bundle-id-matches-input", "status": "PASS"})
            listing = run(["xcrun", "simctl", "list", "devices", "available", "-j"])
            if listing.returncode != 0:
                tests.extend([{"test_id": "simulator-metadata", "status": "BLOCKED"},
                              {"test_id": "simulator-install", "status": "BLOCKED"},
                              {"test_id": "app-launch", "status": "BLOCKED"}])
            else:
                try:
                    inventory = json.loads(listing.stdout)
                except json.JSONDecodeError:
                    inventory = {}
                selected = None
                runtime_name = ""
                for runtime, devices in inventory.get("devices", {}).items():
                    if not isinstance(devices, list):
                        continue
                    for item in devices:
                        if isinstance(item, dict) and item.get("state") == "Booted":
                            selected = item
                            runtime_name = runtime
                            break
                    if selected:
                        break
                if not selected:
                    tests.extend([{"test_id": "simulator-metadata", "status": "BLOCKED"},
                                  {"test_id": "simulator-install", "status": "BLOCKED"},
                                  {"test_id": "app-launch", "status": "BLOCKED"}])
                else:
                    device["model"] = str(selected.get("name") or "unknown")
                    runtime_match = re.search(r"iOS-(\\d+(?:-\\d+)*)", runtime_name)
                    device["os_version"] = runtime_match.group(1).replace("-", ".") if runtime_match else "unknown"
                    tests.append({"test_id": "simulator-metadata", "status": "PASS" if device["model"] else "BLOCKED"})
                    install = run(["xcrun", "simctl", "install", "booted", str(app)], timeout=180)
                    installed = install.returncode == 0
                    tests.append({"test_id": "simulator-install", "status": "PASS" if installed else "FAIL"})
                    if installed:
                        launch = run(["xcrun", "simctl", "launch", "booted", bundle_id], timeout=60)
                        tests.append({"test_id": "app-launch", "status": "PASS" if launch.returncode == 0 and bundle_id in launch.stdout else "FAIL"})
                    else:
                        tests.append({"test_id": "app-launch", "status": "BLOCKED"})
    else:
        tests.extend([{"test_id": "bundle-id-matches-input", "status": "BLOCKED"},
                      {"test_id": "simulator-metadata", "status": "BLOCKED"},
                      {"test_id": "simulator-install", "status": "BLOCKED"},
                      {"test_id": "app-launch", "status": "BLOCKED"}])
    return {"schema": "saqa.native-mobile-evidence.v1", "platform": "ios", "bundle_id": bundle_id,
            "app_sha256": actual, "test_run_id": run_id, "executed_at": datetime.now(timezone.utc).isoformat(),
            "device": device, "tests": tests}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-archive", required=True, type=Path, help="ZIP containing one iOS Simulator .app bundle")
    parser.add_argument("--bundle-id", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    args.output.unlink(missing_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="saqa-ios-smoke-") as temp:
            result = run_smoke(args.app_archive, args.bundle_id, args.expected_sha256, args.run_id, Path(temp))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, ValueError, zipfile.BadZipFile, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"schema": "saqa.native-mobile-evidence.v1", "status": "UNVERIFIED", "error": str(exc)}, indent=2))
        return 2
    status = "FAIL" if any(item["status"] == "FAIL" for item in result["tests"]) else (
        "PASS" if all(item["status"] == "PASS" for item in result["tests"]) else "UNVERIFIED")
    print(json.dumps({"status": status, "platform": "ios", "test_count": len(result["tests"])}, indent=2))
    return 1 if status == "FAIL" else (0 if status == "PASS" else 2)


if __name__ == "__main__":
    raise SystemExit(main())

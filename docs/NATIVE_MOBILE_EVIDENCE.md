# Native mobile evidence contract

The current mobile CI domain tests browser-based readiness. It does not run a native Android or iOS application. Native execution must not be reported as PASS until a real APK/IPA is installed and tested on an identified emulator or device.

## Evidence contract

The Python validator `saqa.native_mobile.validate_native_mobile_evidence` checks the schema `saqa.native-mobile-evidence.v1`, validates platform-specific reverse-domain package/bundle identifiers, and rejects timestamps more than five minutes in the future. Required provenance includes:

- Platform and app package/bundle identifier.
- SHA-256 of the exact Android APK under test. For the current iOS Simulator workflow, this is the ZIP archive digest supplied to the runner, not a digest of the extracted `.app` bundle or an IPA.
- Test run identifier and timezone-aware execution timestamp.
- Device/emulator model, OS version, and runtime.
- A non-empty test list with unique test IDs and explicit PASS/FAIL/BLOCKED/UNVERIFIED results.

Any test failure produces FAIL. If any test is blocked or unverified, the aggregate remains UNVERIFIED rather than passing. All tests must be PASS to derive PASS from the supplied report.

## Example

~~~json
{
  "schema": "saqa.native-mobile-evidence.v1",
  "platform": "android",
  "package_id": "com.example.app",
  "app_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "test_run_id": "run-2026-001",
  "executed_at": "2026-10-21T10:00:00Z",
  "device": {
    "os_version": "Android 15",
    "model": "Pixel_8_API_35",
    "runtime": "emulator"
  },
  "tests": [
    {"test_id": "app-launch", "status": "PASS"}
  ]
}
~~~

The example is illustrative, not executed evidence. Contract validation checks structure and consistency only; it does not authenticate a device run or verify that the binary hash came from a trusted build. Preserve CI/device logs and signed artifact provenance. Native execution remains UNVERIFIED until an authorized app artifact and real emulator/device workflow are configured.


## Validate an evidence file

Once a real device/emulator runner has produced the JSON document, normalize and validate it with:

~~~bash
python scripts/validate_native_mobile_evidence.py \
  --input artifacts/native-mobile/raw-evidence.json \
  --output artifacts/native-mobile/validated-evidence.json
~~~

Exit code 0 means all reported tests passed; 1 means at least one reported test failed; 2 means evidence is invalid or incomplete. This command does not install or launch an APK/IPA and must not be treated as a native execution workflow.


## Executable Android emulator smoke workflow

The repository includes a manual workflow at `.github/workflows/saqa-native-android.yml`. It downloads an APK asset from a GitHub Release **in this same repository**, verifies the exact expected SHA-256, installs it on a Pixel 8 / Android API 35 emulator, attempts to launch the declared package, and uploads normalized native evidence.

To run it, first publish an authorized APK as a release asset, then use **Actions → SAQA Native Android Smoke → Run workflow** and provide the release tag, exact APK filename, package ID, and independently obtained expected SHA-256. Do not use an APK from an untrusted source. The workflow is manual-dispatch only and does not run against a production service.

Coverage is intentionally limited to artifact hash, install, and launch smoke checks. It is **not** an Appium functional suite, lifecycle/permission suite, physical-device matrix, or iOS test. A workflow file existing is not a passing run: native Android remains UNVERIFIED until a real release APK is supplied and the workflow produces fresh passing evidence. iOS still requires a separate macOS/Xcode simulator or device runner.


## Executable iOS Simulator smoke workflow

The repository also includes `.github/workflows/saqa-native-ios.yml`, a manual-dispatch workflow for a trusted iOS Simulator build. It downloads a ZIP containing exactly one simulator-compatible `.app` bundle from a GitHub Release in this repository, checks the independently obtained ZIP SHA-256, verifies `CFBundleIdentifier`, installs and launches the app on an available iPhone simulator, and uploads normalized evidence.

To run it, publish a simulator-built `.app` bundle as a ZIP release asset, then use **Actions → SAQA Native iOS Simulator Smoke → Run workflow** with the release tag, exact asset filename, bundle ID, and independently verified SHA-256. A device-targeted IPA is generally not a substitute for a simulator-compatible `.app` bundle. The workflow does not run on every pull request and does not claim physical-device coverage, Appium functional coverage, permissions/lifecycle coverage, or App Store signing validation. iOS remains UNVERIFIED until a real authorized simulator artifact is supplied and the workflow passes.

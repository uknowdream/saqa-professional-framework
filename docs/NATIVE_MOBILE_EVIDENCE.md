# Native mobile evidence contract

The current mobile CI domain tests browser-based readiness. It does not run a native Android or iOS application. Native execution must not be reported as PASS until a real APK/IPA is installed and tested on an identified emulator or device.

## Evidence contract

The Python validator `saqa.native_mobile.validate_native_mobile_evidence` checks the schema `saqa.native-mobile-evidence.v1`. Required provenance includes:

- Platform and app package/bundle identifier.
- SHA-256 of the exact APK/IPA under test.
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

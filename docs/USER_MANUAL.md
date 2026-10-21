# SAQA Professional Framework — User Manual

This manual describes how to operate the current repository safely. It complements the root [README](../README.md), architecture notes, and per-capability guides; it is not evidence that a particular application has passed certification.

## 1. Operating principles

SAQA keeps execution, evidence validation, and certification separate.

- **PASS** means a check ran and its assertions passed with the required evidence.
- **FAIL** means a check ran and detected a quality or policy failure.
- **BLOCKED** means a prerequisite prevented reliable execution.
- **UNVERIFIED** means the available evidence cannot support a conclusion.
- **NOT_CERTIFIED** means the release gate did not accept all mandatory evidence.

Never convert missing evidence, an unavailable device, stale artifacts, an unknown status, or an incomplete run into PASS. Do not weaken assertions solely to make CI green.

## 2. Install and validate the framework

Requirements: Python 3.11 or newer, Git, and Docker for the local reference target workflows.

~~~bash
git clone https://github.com/uknowdream/saqa-professional-framework.git
cd saqa-professional-framework
python -m venv .venv
~~~

Activate the environment and install test dependencies:

~~~bash
# Linux/macOS
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[test,ci]"
~~~

~~~powershell
# Windows PowerShell
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[test,ci]"
~~~

Run local unit and regression tests:

~~~bash
python -m pytest
~~~

A local unit-test pass validates the framework code exercised by that suite; it does not certify a running target application or production environment.

## 3. Run the authorized local reference target

Start the pinned OWASP Juice Shop container, bound to loopback only:

~~~bash
docker run --detach --rm --name saqa-juice-shop -p 127.0.0.1:3000:3000 bkimminich/juice-shop:v20.2.0
~~~

Install the Playwright version used by CI and its browser binaries:

~~~bash
python -m pip install "playwright==1.62.0"
python -m playwright install chromium firefox webkit
~~~

Execute reference checks:

~~~bash
python scripts/juice_shop_e2e.py
python scripts/juice_shop_api_smoke.py
python scripts/database_quality_gate.py
~~~

The E2E/API workflows are intended for the local reference target. The database gate uses isolated SQLite `:memory:` storage and does not connect to an external database.

Stop the target when finished:

~~~bash
docker stop saqa-juice-shop
~~~

## 4. Accessibility, mobile readiness, and performance

The browser-based accessibility gate uses a pinned axe-core oracle. With Juice Shop running and axe-core installed as described in the README:

~~~bash
SAQA_BROWSER=chromium SAQA_AXE_CORE_PATH=node_modules/axe-core/axe.min.js python scripts/juice_shop_accessibility_gate.py
~~~

The automated result is an accessibility readiness assessment for selected rules. It is not complete WCAG conformance. Follow [the manual accessibility plan](ACCESSIBILITY_MANUAL_TEST_PLAN.md) and preserve actual keyboard/screen-reader observations; unexecuted checks remain UNVERIFIED.

The current mobile readiness executor checks a narrow browser viewport across browser engines; it is not native Android/iOS evidence:

~~~bash
SAQA_BROWSER=chromium python scripts/juice_shop_mobile_readiness.py
~~~

For response-time readiness and the versioned k6 gate, use the relevant README instructions and [k6 performance guide](K6_PERFORMANCE.md). Optional exploratory workloads are GET-only and loopback-restricted:

~~~bash
SAQA_K6_PROFILE=smoke k6 run performance/k6/juice-shop-scenarios.js
SAQA_K6_PROFILE=load k6 run performance/k6/juice-shop-scenarios.js
~~~

For repeated-run regression screening, use [the performance baseline comparison guide](PERFORMANCE_BASELINE_COMPARISON.md). It requires measured, metadata-compatible run sets with at least five samples on each side. Do not fabricate samples or promote a baseline automatically; the median comparison is not a statistical significance test or production SLO.

## 5. Evidence and certification

Evidence artifacts normally live under `artifacts/`. Typical metadata includes schema, test ID, status, target, execution timestamp, browser/platform details, and run/commit provenance. Canonical aggregation validates structure and generates SHA-256 manifest integrity metadata.

A SHA-256 manifest identifies bytes and detects accidental or uncoordinated tampering; it is not a digital signature or proof of a trusted producer by itself. Release certification uses exact-commit GitHub Actions runs and required evidence artifacts. A release can be NOT_CERTIFIED even if some independent workflow passed.

For evidence retention, checksum verification, exact-SHA recovery, and expired/missing-artifact handling, follow [Artifact Retention and Recovery](ARTIFACT_RETENTION_AND_RECOVERY.md).

## 6. Native Android/iOS execution

The repository includes manual-dispatch Android emulator and iOS Simulator workflows. Both require an authorized real application artifact published as a GitHub Release asset, an app/package or bundle identifier, and an independently verified SHA-256 digest.

- Android accepts an APK, installs it on an Android emulator, attempts an app launch, and verifies that the app process remains alive.
- iOS accepts a ZIP containing a simulator-compatible `.app` bundle, verifies the bundle identifier, installs it on an iPhone Simulator, and attempts a launch.

See [Native Mobile Evidence](NATIVE_MOBILE_EVIDENCE.md) for exact release-asset requirements and evidence semantics. A workflow file or a unit-test mock is not a native device pass. These smoke workflows are not full Appium functional suites, permission/lifecycle suites, physical-device matrices, or App Store signing validation.

## 7. Security, target authorization, and integrations

Use only local/containerized reference targets or systems explicitly authorized for the test. Never put API tokens, credentials, private keys, or other secrets into the repository or evidence. Do not run destructive actions against reference targets unless a dedicated isolated fixture requires them.

The pinned Juice Shop training image is intentionally vulnerable and remains report-only. A security maintainer still needs to review the six embedded secret-pattern matches before any finding is classified as a confirmed placeholder or exception. Do not copy a training-image exception to a production image or application.

Jira synchronization depends on the repository's Jira URL/project settings and the `JIRA_API_TOKEN` secret. External Jira project access cannot be inferred from local unit tests; use [Jira CI](JIRA_CI.md) for setup and recovery.

The main-branch protection audit is documented in [Branch Protection Audit](BRANCH_PROTECTION_AUDIT.md). It requires the `SAQA_REPO_ADMIN_AUDIT_TOKEN` repository secret with Administration: read-only permission. Until the workflow can read the actual GitHub settings and records PASS, branch protection is UNVERIFIED; the audit does not change repository settings.

## 8. Troubleshooting and defect handling

When a target or dependency is unavailable, diagnose the environment before changing application assertions. Inspect the failing workflow job and its artifact, verify the exact commit/run ID, and compare the local environment with the pinned CI versions. Do not reuse evidence from an earlier commit or run attempt.

A useful defect record includes:

1. Title and severity/priority.
2. Exact target/build, commit, OS/browser/device, and test run ID.
3. Preconditions and reproducible steps.
4. Expected and actual behavior.
5. Logs, screenshots, traces, or other relevant evidence with secrets redacted.
6. Owner, fix, and retest result.

After a change, run targeted tests first and the relevant full CI matrix afterward. Certification follows verified evidence; it is not a substitute for reviewing the underlying failure.

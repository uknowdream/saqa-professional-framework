# SAQA Professional Framework — Known Limitations and Next Priorities

Last reviewed: 2026-10-22  
Main-branch certified commit at review: `9ffeb5c6206d5c1786e8cb0d1b3652f6a37bc6e1` (PR #16 merged on 2026-10-21).

## Current verified baseline

The post-merge release certification workflow [run 39658922347](https://github.com/uknowdream/saqa-professional-framework/actions/runs/39658922347) completed successfully for exact main commit `9ffeb5c6206d5c1786e8cb0d1b3652f6a37bc6e1`. The five mandatory domains were all `PASS` with fresh evidence bound to that exact commit. The push-triggered CI, contract, accessibility, mobile-readiness, k6, advanced-QE, contract-mock, framework-integrity, and container-security workflows also completed successfully for that commit. The training-image security scan is report-only and does not constitute production security certification.

- SAQA CI
- SAQA Contract Testing
- SAQA Accessibility
- SAQA Mobile Readiness
- SAQA k6 Performance

This is a commit-scoped CI certification, not a claim that every possible application, device, browser version, production environment, or security scenario has been tested.

## Scope boundaries

- **Mobile:** current mobile readiness coverage is browser/device-oriented readiness in the CI matrix. It is not equivalent to end-to-end testing on a physical Android/iOS device or a native application test suite.
- **Accessibility:** automated axe-core checks cover selected rules and pages. They do not replace full WCAG conformance evaluation, manual keyboard/screen-reader testing, or human review.
- **Performance:** the mandatory CI gate validates a short reference workload; separate local-only smoke/load/stress/spike/soak profiles support exploratory characterization. Neither alone predicts production capacity without representative traffic, infrastructure, repeated runs, and service-level objectives.
- **Security:** CI runs Bandit SAST against `src/` and `scripts/` for high-severity/high-confidence findings, generates a CycloneDX SBOM for the installed Python environment and an SPDX JSON SBOM for the pinned Juice Shop training image, audits Python dependencies, checks configured secret patterns, and scans the training image with Trivy 0.76.0. The image SBOM is structurally validated, its SHA-256 is retained in validation evidence, and its raw SPDX document receives a GitHub provenance attestation only through a separate trusted-main job; PR and non-main runs skip attestation publication. The scanner policy supports severity-based blocking and exact, expiring exceptions, but this intentionally vulnerable training image is run in report-only mode and is not a release-security certification. Attestation authenticates workflow provenance, not SBOM completeness or security correctness. These SBOMs do not cover every runtime/deployment artifact of an unrelated production application.
- **Targets:** CI uses authorized, reproducible reference targets such as Juice Shop and WebGoat. Results should not be interpreted as proof about an unrelated product or deployment.
- **Evidence:** SHA-256 manifests provide integrity/tamper evidence for collected records; they are not a digital signature or proof of a trusted identity by themselves.
- **Integrations:** Jira automation depends on repository configuration, permissions, and secrets being correctly provisioned. A passing repository workflow does not prove every external Jira project or tenant is configured correctly.

## Next engineering priorities

### P1 — Native mobile execution
- [x] Define and test a fail-closed native Android/iOS evidence contract requiring the app hash, package/bundle ID, test-run ID, timezone-aware timestamp, device/OS/runtime metadata, and explicit per-test status.
- [x] Add manual-dispatch Android emulator install/launch smoke for a hash-verified APK release asset.
- [x] Add manual-dispatch iOS Simulator install/launch smoke for a hash-verified simulator-compatible .app ZIP release asset.
- [x] Capture OS/runtime, model, package/bundle identifier, artifact SHA-256, and test-run identifiers in native evidence.
- Native workflows exist but require an authorized app artifact and a real successful run; neither platform is considered certified until fresh device/emulator evidence is produced. Physical-device, lifecycle, permission, Appium, and broad iOS coverage remain out of scope.

### P1 — Accessibility depth
- [x] Record keyboard Tab traversal, focus-visible state, CSS focus-indicator clues, repeated consecutive focus targets, and a conservative suspected-trap diagnostic in accessibility evidence.
- [x] Repeat keyboard-only traversal at a narrow 390×844 viewport after a fresh page load; this is browser-based mobile viewport coverage, not native-device evidence.
- Manual focus-order, keyboard-trap, and visible-indicator verification remains required; the diagnostic is not treated as conformance proof.
- [x] Add a manual keyboard-only and screen-reader test matrix mapped to WCAG 2.2 criteria (`docs/ACCESSIBILITY_MANUAL_TEST_PLAN.md`).
- [x] Add a fail-closed validator for the complete 14-case manual result matrix, including named tester, exact target commit, environment/assistive-technology versions, evidence references, and strict PASS/FAIL/BLOCKED/UNVERIFIED/N/A semantics (`scripts/validate_accessibility_manual_evidence.py`).
- Manual execution and results remain UNVERIFIED until a tester records environment-specific evidence; the validator checks the submitted record, not the underlying physical testing.
- Keep unsupported criteria labelled `UNVERIFIED`; do not infer full conformance from an automated scan.

### P1 — Performance confidence
- [x] Add local-only smoke/load/stress/spike/soak workload profiles for the authorized Juice Shop target.
- [x] Collect ten independent guarded k6 runs as two five-run groups on one runner and compare median/p95/p99, error rate, throughput, and functional check rate using raw-summary, policy, and exact workload-script SHA-256 provenance.
- [x] Add a builder that converts at least five distinct raw k6 summaries into a run set with per-file SHA-256 records and source-root confinement.
- [x] Add a manual/weekly workflow to collect ten independently executed guarded samples as two five-run groups on one runner, retain raw evidence, and run a same-environment repeatability comparison; failed absolute guardrails or a blocked/failed comparison fail the workflow.
- [x] Add a deterministic repeated-run comparator that verifies raw sample hashes and metric binding, binds run sets to the exact canonical policy SHA-256 and exact k6 workload-script SHA-256, blocks fewer than five samples or mismatched target/workload/policy/environment metadata, and compares median/p95/p99 latency, error rate, throughput, and functional check rate.
- The comparator is available through a manually dispatched workflow, not a mandatory release-certification domain; no synthetic baseline is committed. A baseline must be reviewed from archived, verified repeated-run artifacts before it can support release decisions.

### P2 — Security coverage
- [x] Add a threat-model template and a risk-to-test traceability matrix.
- [x] Generate and publish a CycloneDX Python-environment SBOM and retain machine-readable dependency-audit output in CI.
- [x] Generate an SPDX JSON SBOM for the pinned reference container, validate document/package structure, and record the raw artifact SHA-256.
- [x] Attest and verify the raw SPDX SBOM in a separate job restricted to trusted `main`-branch runs; PR and non-main runs do not receive OIDC/attestation-write permissions.
- [x] Add a dedicated Trivy image/secret/misconfiguration scan workflow for the pinned Juice Shop reference image and retain JSON evidence.
- [x] Fail closed on malformed Trivy report structure, malformed finding arrays, and unsupported severity values before writing a normalized summary.
- [x] Enforce a versioned Trivy policy: any secret finding, HIGH/CRITICAL misconfiguration, and CRITICAL vulnerability blocks the security workflow unless an exact-match, unexpired exception names a reason, owner, ticket, and expiry date.
- [x] Record first-pass triage for the pinned training-image scan, including finding counts, exact workflow/run provenance, raw report hashes, and the report-only disposition in `docs/security/REFERENCE_IMAGE_TRIAGE_2026-10-21.md`.
- The intentionally vulnerable image remains report-only and is not a mandatory release-certification domain. A human security maintainer still must verify the six embedded secret-pattern matches before treating them as confirmed placeholders or adding exceptions.
- Keep active security tests restricted to isolated, explicitly authorized targets.

### P2 — Evidence trust and operations
- [x] Configure GitHub artifact provenance attestation for the CycloneDX SBOM on non-PR trusted runs; pull-request runs skip publishing attestations.
- [x] Verify SBOM provenance attestation on non-PR trusted runs with GitHub CLI; pull-request runs skip attestation publication and verification. Keep SHA-256 manifest verification as a separate integrity check.
- [x] Add release-report freshness checks: evidence must have timezone-aware timestamps and default to a 24-hour maximum age (configurable with `SAQA_MAX_EVIDENCE_AGE_HOURS`).
- [x] Delete any prior native-mobile validation output or `CERTIFIED` release report before re-validating, so an invalid rerun cannot leave stale PASS evidence on disk.
- [x] Document artifact retention periods, checksum verification, exact-SHA recovery, and the rule that missing/expired evidence leaves certification NOT_CERTIFIED (`docs/ARTIFACT_RETENTION_AND_RECOVERY.md`).
- [x] Add a daily API-level artifact retention audit that reads exact-workflow run and artifact metadata for current `main`, rejects missing/empty/expired/near-expiry artifacts and artifacts predating the selected attempt, and uploads its decision report. It requires the configured GitHub Actions `actions: read` permission.
- Verify branch protection and required-check configuration in repository settings; this integration currently may not have permission to read branch-protection settings.

### P2 — Maintainability
- [x] Schedule the CI dependency audit, CycloneDX SBOM generation, and compatibility matrix weekly (Monday 04:17 UTC), in addition to PR/push runs.
- [x] Schedule the pinned reference-container Trivy scan weekly (Monday 04:43 UTC), in addition to PR/push runs.
- A successful scan means the scanner ran and produced a validated report. The pinned intentionally vulnerable Juice Shop scan is report-only by design; apply the versioned blocking policy to authorized non-training targets before treating findings as release-blocking.
- [x] Publish JUnit test count, failure/skip rate, aggregate duration, and slowest-test list; validate an owner/ticket/reason/expiry quarantine registry in CI.
- [x] Add cross-run JUnit outcome history by Python-version cohort, with same-commit variation separated from cross-commit differences and missing artifacts reported as gaps (`docs/TEST_STABILITY_HISTORY.md`).
- [x] Add retry-aware per-attempt telemetry with pinned `pytest-rerunfailures`, per-worker JSON evidence, run/commit/Python provenance, and a fail-closed summary gate.
- [x] Detect failure-then-pass retry variation without copying failure text into telemetry; the CI quality job fails rather than silently accepting recovered failures.
- A retry outcome variation is a candidate intermittent result requiring investigation, not proof of intrinsic flakiness. Cross-commit outcome variation remains separate.
- Keep the release report and roadmap synchronized with actual workflow evidence.

## Definition of done for future work

A priority is complete only when its implementation, automated tests, documentation, and fresh evidence are available. New mandatory domains must be wired into the certification gate before their results can affect release status. No domain may be marked `PASS` based only on source inspection or a successful unrelated workflow.

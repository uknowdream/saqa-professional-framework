# SAQA Professional Framework — Known Limitations and Next Priorities

Last reviewed: 2026-10-20  
Main-branch certified commit at review: `872bf0d182f3287d7e519947a259cc3313e51ed0`

## Current verified baseline

The post-merge release certification workflow reported `CERTIFIED` for the commit above. The five mandatory domains were all `PASS` with fresh evidence bound to that exact commit:

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
- **Security:** CI generates a CycloneDX SBOM, audits Python dependencies, checks secret patterns, and scans the pinned Juice Shop image with Trivy 0.76.0 for vulnerabilities, secrets, and misconfiguration. The workflow verifies the runtime version and derives report metadata from the same pinned version variable. The Trivy workflow currently retains findings in report-only mode pending triage; it is not yet a release-blocking severity/exception policy and does not replace a penetration test or external assessment. The SBOM covers the installed CI Python environment.
- **Targets:** CI uses authorized, reproducible reference targets such as Juice Shop and WebGoat. Results should not be interpreted as proof about an unrelated product or deployment.
- **Evidence:** SHA-256 manifests provide integrity/tamper evidence for collected records; they are not a digital signature or proof of a trusted identity by themselves.
- **Integrations:** Jira automation depends on repository configuration, permissions, and secrets being correctly provisioned. A passing repository workflow does not prove every external Jira project or tenant is configured correctly.

## Next engineering priorities

### P1 — Native mobile execution
- Add an explicit Android emulator/device workflow and document iOS coverage requirements.
- Capture device OS, model/emulator image, app build, and test-run identifiers in evidence.
- Keep this domain separate from browser-based mobile readiness until it has independent passing evidence.

### P1 — Accessibility depth
- Add keyboard-only navigation checks and focus-order assertions for representative flows.
- [x] Add a manual keyboard-only and screen-reader test matrix mapped to WCAG 2.2 criteria (`docs/ACCESSIBILITY_MANUAL_TEST_PLAN.md`).
- Manual execution and results remain UNVERIFIED until a tester records environment-specific evidence.
- Keep unsupported criteria labelled `UNVERIFIED`; do not infer full conformance from an automated scan.

### P1 — Performance confidence
- [x] Add local-only smoke/load/stress/spike/soak workload profiles for the authorized Juice Shop target.
- Add repeatability checks and preserve p50/p95/p99, error rate, throughput, and environment metadata for exploratory profiles.
- [x] Add a deterministic repeated-run median comparator that blocks on fewer than five samples, invalid metrics, and mismatched target/workload/policy/environment metadata.
- The comparator is an explicit CLI workflow, not a mandatory release-certification domain; no synthetic baseline is committed.

### P2 — Security coverage
- [x] Add a threat-model template and a risk-to-test traceability matrix.
- [x] Generate and publish a CycloneDX SBOM and retain machine-readable dependency-audit output in CI.
- [x] Add a dedicated Trivy image/secret/misconfiguration scan workflow for the pinned Juice Shop reference image and retain JSON evidence.
- [x] Fail closed on malformed Trivy report structure, malformed finding arrays, and unsupported severity values before writing a normalized summary.
- The initial scan remains report-only pending finding triage; it does not yet enforce a release-blocking severity policy or exception expiry.
- Keep active security tests restricted to isolated, explicitly authorized targets.

### P2 — Evidence trust and operations
- Add signed attestations or artifact attestations where supported; keep SHA-256 manifest verification as a separate integrity check.
- [x] Add release-report freshness checks: evidence must have timezone-aware timestamps and default to a 24-hour maximum age (configurable with `SAQA_MAX_EVIDENCE_AGE_HOURS`).
- [x] Document artifact retention periods, checksum verification, exact-SHA recovery, and the rule that missing/expired evidence leaves certification NOT_CERTIFIED (`docs/ARTIFACT_RETENTION_AND_RECOVERY.md`).
- Automated API-level artifact-expiry discovery remains dependent on repository token permissions and is not represented as implemented.
- Verify branch protection and required-check configuration in repository settings; this integration currently may not have permission to read branch-protection settings.

### P2 — Maintainability
- [x] Schedule the CI dependency audit, CycloneDX SBOM generation, and compatibility matrix weekly (Monday 04:17 UTC), in addition to PR/push runs.
- [x] Schedule the pinned reference-container Trivy scan weekly (Monday 04:43 UTC), in addition to PR/push runs.
- A successful scan means the scanner ran and produced a validated report; vulnerability findings remain report-only until a reviewed severity/exception policy is introduced.
- Track flaky-test rate, test duration, retry rate, and quarantined tests with owner and expiry.
- Keep the release report and roadmap synchronized with actual workflow evidence.

## Definition of done for future work

A priority is complete only when its implementation, automated tests, documentation, and fresh evidence are available. New mandatory domains must be wired into the certification gate before their results can affect release status. No domain may be marked `PASS` based only on source inspection or a successful unrelated workflow.

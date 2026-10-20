# SAQA Professional Framework — Known Limitations and Next Priorities

Last reviewed: 2026-10-20  
Certified commit at review: `02a4fda27fc63f234809000082bc9a498cf9af98`

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
- **Performance:** k6 and response-time gates validate the configured reference workload and thresholds. They do not predict production capacity without representative traffic models, infrastructure, and service-level objectives.
- **Security:** authorized isolated-target regressions and dependency/secret checks are a safety baseline, not a full penetration test, threat model, or external vulnerability assessment.
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
- Add documented manual screen-reader test cases and a WCAG mapping for automated/manual coverage.
- Keep unsupported criteria labelled `UNVERIFIED`; do not infer full conformance from an automated scan.

### P1 — Performance confidence
- Version workload profiles and thresholds alongside the application target.
- Add repeatability checks and preserve p50/p95/p99, error rate, throughput, and environment metadata.
- Define a separate baseline-comparison gate before making regression claims.

### P2 — Security coverage
- Add a threat-model template and a risk-to-test traceability matrix.
- Add SBOM generation and artifact publication, plus vulnerability scanning with explicit severity policy and exception expiry.
- Keep active security tests restricted to isolated, explicitly authorized targets.

### P2 — Evidence trust and operations
- Add signed attestations or artifact attestations where supported; keep SHA-256 manifest verification as a separate integrity check.
- Add retention/expiry checks and a documented recovery procedure for missing or expired artifacts.
- Verify branch protection and required-check configuration in repository settings; this integration currently may not have permission to read branch-protection settings.

### P2 — Maintainability
- Add a scheduled dependency-update and compatibility review.
- Track flaky-test rate, test duration, retry rate, and quarantined tests with owner and expiry.
- Keep the release report and roadmap synchronized with actual workflow evidence.

## Definition of done for future work

A priority is complete only when its implementation, automated tests, documentation, and fresh evidence are available. New mandatory domains must be wired into the certification gate before their results can affect release status. No domain may be marked `PASS` based only on source inspection or a successful unrelated workflow.

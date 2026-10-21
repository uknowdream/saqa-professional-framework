# Security Risk-to-Test Traceability Matrix

This is a starter matrix, not proof that the system is secure. Adapt each row to the application's architecture, and attach evidence for every executed test.

| Risk area | Example threat | Minimum verification | Evidence expectation | Default status |
| --- | --- | --- | --- | --- |
| Authentication | Session or token misuse | Login/logout, expiry, invalid-token and recovery tests | Test ID, target/build SHA, result, timestamp | UNVERIFIED |
| Authorization | Cross-user or privileged access | Role/tenant access matrix with negative cases | Per-role allow/deny evidence | UNVERIFIED |
| Input validation | Injection or path traversal | Safe, non-destructive payloads against isolated target | Request/response summary, no secrets | UNVERIFIED |
| API controls | Missing limits or unsafe errors | Schema, status-code, pagination, rate-limit checks | Contract test report | UNVERIFIED |
| Data exposure | Sensitive data in response/logs | Error-path and logging review with synthetic data | Redacted evidence | UNVERIFIED |
| Dependency supply chain | Known vulnerable package | pip-audit plus CycloneDX SBOM review | SBOM artifact and JSON audit artifact | CI-verified only when workflow passes |
| Secret exposure | Committed credential or private key | Secret scanner plus repository history review | Scanner output and triage record | CI-verified only for configured patterns |
| Container image | Vulnerable OS/library package, embedded secret, unsafe configuration | Pinned Trivy scan, schema validation, then versioned policy evaluation with exact-match expiring exceptions | Scanner version, image tag, normalized findings, policy result, exception owner/ticket/expiry | Secrets, HIGH/CRITICAL misconfiguration, and CRITICAL vulnerabilities block the security workflow unless covered by a valid exact exception; other vulnerability severities remain report-only |
| Configuration | Debug mode, permissive CORS, unsafe headers | Environment/config review and safe HTTP checks | Config snapshot without secrets | UNVERIFIED |
| Availability | Resource exhaustion | Authorized load limits and recovery checks | Workload profile, duration, resource/error metrics | UNVERIFIED |
| Accessibility / privacy | Data leakage to assistive or analytics surfaces | Manual and automated review where relevant | WCAG/privacy mapping and reviewer | UNVERIFIED |

## Release interpretation
- PASS means the specified test ran against the declared target/build and passed its acceptance criteria.
- FAIL means a test ran and did not meet its acceptance criteria.
- BLOCKED means execution was prevented by an environmental or authorization constraint.
- UNVERIFIED means there is not sufficient evidence to make a claim.
- Do not promote an entire risk area to PASS based on one representative test.
- Active security tests must remain within explicitly authorized targets.
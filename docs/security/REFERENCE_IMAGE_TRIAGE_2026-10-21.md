# Reference-image security triage snapshot — 2026-10-21

## Scope and provenance

This is a first-pass triage of the preserved report from the **intentionally vulnerable OWASP Juice Shop training image**, not a production-image security sign-off.

- Repository: `uknowdream/saqa-professional-framework`
- Workflow: [SAQA Container Security run 39620746267](https://github.com/uknowdream/saqa-professional-framework/actions/runs/39620746267)
- Scanned source commit: `5c0a5092b0c6840e974bcee8ad8a277eb8a8ab87`
- Image: `bkimminich/juice-shop:v20.2.0`
- Scanner: Trivy `0.76.0`
- Artifact: `saqa-container-security-eadf31afe9a9228e08ab4f115cff2689d899a088` (artifact ID `12354128930`)
- Normalized finding count: 267
- Normalized summary SHA-256: `5a16c12788ff101515f4cf47dfbc2c4de175ad1bfde7f8742518d54557f47432`
- Policy result SHA-256: `391dc19297dc554eae741dc07f567a6a136a4aa7aa7c28fb408f47b8f33424f5`
- SBOM validation SHA-256: `009ef67783d63edaf2a0398103f215db9b3f7e6c4f2b1871c81e1be122d3ffa1`

The SBOM validator reported SPDX 2.3 and 713 packages, with a structurally valid report. Structural validation does not prove SBOM completeness or scanner authenticity.

## Observed findings

| Type | Critical | High | Medium | Low | Total |
|---|---:|---:|---:|---:|---:|
| Vulnerability | 12 | 54 | 88 | 24 | 178 |
| Secret pattern | 0 | 4 | 2 | 0 | 6 |
| Misconfiguration | 20 | 20 | 5 | 38 | 83 |
| **Total** | **32** | **78** | **95** | **62** | **267** |

The versioned policy currently marks 58 findings as blocking *signals* before exception handling: 12 critical vulnerability findings, 40 critical/high misconfiguration findings, and six secret-pattern findings. The evaluator output is `REPORT_ONLY`, has zero suppressions, and explicitly sets `release_gate_eligible: false` for this training image.

## Triage disposition

1. **Vulnerabilities (178 findings).** Keep unresolved findings visible. This is a training image that is deliberately vulnerable; its report must not be interpreted as the vulnerability posture of a production app. Do not add blanket CVE or severity exceptions. Any future production-image decision needs its own target, versioned policy, remediation review, and run-bound evidence.
2. **Misconfigurations (83 findings).** The highest-severity findings include IaC exercise files named `iacLeakedKeyChallenge_*.tf` and sample Terraform networking files inside the pinned training image. Retain them in the training report. Do not use these findings as a release decision for unrelated deployment infrastructure.
3. **Secret patterns (six findings).** Trivy reported four HIGH `private-key` patterns in `insecurity.js` and Terraform exercise/sample files, plus two MEDIUM `jwt-token` patterns in test-spec files. Their location is consistent with training content, but location alone does **not** prove that a value is safe. A human security maintainer must inspect the exact bytes in the original pinned image and confirm they are synthetic test material before recording any exception. Do not copy the detected values into issue text, logs, or this repository.
4. **Policy and exceptions.** The checked-in policy has no active exceptions. Keep it that way until a named owner, ticket, written reason, exact finding type/ID/severity/target, and future expiry date are recorded and reviewed. The evaluator rejects wildcard exceptions and expired exceptions.
5. **Release gating.** Continue report-only mode for the intentionally vulnerable Juice Shop image. Do not make its known training findings a mandatory release blocker, and do not claim security certification from this scan. Apply blocking mode only to a separately identified target after its risk policy has been explicitly reviewed.

## Open manual action

**Human review remains required:** assign a security owner to inspect and confirm the six embedded secret-pattern matches are placeholders/test fixtures. Until that review is recorded, they are *expected-location findings awaiting confirmation*, not declared false positives and not silently suppressed. The current automated CI scans the repository independently for configured secret patterns.

This snapshot documents the observed report and its current disposition. It is not automatically updated when Trivy, the image, or its contents change; review the artifact from the latest successful container-security workflow before making a new decision.

# SAQA CI artifact retention and recovery runbook

## Retention policy

Workflows upload evidence artifacts with explicit retention periods:
- Core CI, browser, API, accessibility, mobile, and performance evidence: typically 14 days.
- Security scan, SBOM, dependency audit, and release readiness/certification reports: 30 days.

Retention is a GitHub Actions artifact policy, not a long-term archive guarantee. If a release needs evidence beyond the configured retention, copy the exact run's artifacts into the organization's approved immutable evidence store and record the repository, workflow run ID, attempt, commit SHA, artifact name, download time, and checksum. Do not store credentials or unredacted sensitive data in the archive.

## Recovery procedure

1. Open the commit's Actions runs and identify the exact expected workflow, run ID, attempt, and commit SHA.
2. Download the artifact only from that run. Verify the artifact's commit/run metadata and manifest SHA-256 before using it.
3. If the artifact is missing, expired, malformed, or bound to another SHA, do not substitute an artifact from a neighboring commit. The release remains `NOT_CERTIFIED`.
4. For a current `main` commit, rerun the relevant workflow from the Actions UI when the workflow supports re-run, or use its `workflow_dispatch` input where available. The release-certification workflow's manual input must be the full intended commit SHA.
5. Wait for the required domains to complete successfully and rerun release certification. The gate independently checks exact commit, expected workflow identity, successful conclusion, current `main`, and evidence freshness.
6. If a rerun is not possible or the commit is no longer current `main`, create a reviewed follow-up commit and rerun the required matrix. Do not edit a certification report to make it pass.
7. Record the incident, missing artifact name, affected run, recovery action, and final certification report link in the release/change record.

## Operational checks

- Verify retention settings after changing workflows; keep `if-no-files-found: error` for artifacts required to interpret a gate.
- Keep `if: always()` on evidence-upload steps where failure evidence is important, but never allow an absent mandatory artifact to become a PASS.
- Keep security findings and raw scanner reports paired with the normalized summary and scanner version.
- Review repository storage limits and organizational retention policy periodically.
- Artifact hashes detect modification only when the expected hash is independently preserved; a hash alone is not a signed identity attestation.

## SBOM provenance attestation

On trusted non-pull-request runs, the dependency/security job publishes a GitHub artifact provenance attestation for `artifacts/security/sbom.cdx.json`. Pull-request runs intentionally skip attestation publication. An attestation establishes provenance claims for the artifact; it does not mean the SBOM has no vulnerabilities or that the application is secure.

After downloading the SBOM from a trusted run, verify it with GitHub CLI:

~~~bash
gh attestation verify artifacts/security/sbom.cdx.json --repo uknowdream/saqa-professional-framework
~~~

Verify that the reported source repository, workflow identity, and commit correspond to the expected trusted run before relying on the file. If no attestation is available, verification fails, or the source identity/commit differs, treat provenance as unverified and recover the artifact from the exact trusted run. Continue to validate the SBOM contents and dependency-audit result separately.


## Release certification provenance attestation

The trusted release-certification workflow now attests `artifacts/release-certification.json` only after the certification evaluator exits successfully, which requires a `CERTIFIED` decision. The same workflow verifies the resulting GitHub artifact attestation before uploading the report. A failed, blocked, stale, or unverified decision is not attested as a successful release certification.

The attestation establishes artifact provenance from the trusted workflow; it does not establish application security, completeness of test coverage, or production readiness. Keep the report's commit SHA, mandatory-domain results, and evidence freshness checks as separate release controls.

# Supply-chain security policy

## SBOM

The `SAQA Supply Chain Security` workflow generates a CycloneDX JSON inventory of the Python environment and uploads it with the raw vulnerability report and policy decision. Artifacts are commit-specific and retained for 30 days. Review the generated SBOM before release and keep a copy with the release evidence where required by your delivery process.

## Vulnerability gate

The workflow runs pinned `pip-audit` and evaluates its JSON report using `security/vulnerability-policy.json`.

- The current blocking threshold is **HIGH**.
- `pip-audit` does not consistently provide CVSS severity in its JSON output. Findings without a recognized `LOW`, `MEDIUM`, `HIGH`, or `CRITICAL` severity are therefore classified as **HIGH** by default. This is deliberately fail-closed; it is not a claim that every unscored issue has a measured HIGH CVSS score.
- A finding at or above the threshold blocks the workflow unless a precise, unexpired exception matches it.
- The evaluator accepts exceptions only for the exact normalized package name and exact vulnerability ID or one of its aliases. Package substring matches are not accepted.
- Every exception requires a reason, accountable owner, and ISO date `expires_on` (`YYYY-MM-DD`). An expired exception fails the policy even if its finding is absent from the latest scan, forcing stale exceptions to be removed or renewed explicitly.
- The default exception list is empty. Do not add broad package-wide suppressions or permanent exceptions.

## Adding an exception

Add an entry to the `exceptions` array in `security/vulnerability-policy.json` only after a documented risk decision. Example shape:

```json
{
  "package": "example-package",
  "vulnerability_id": "CVE-2026-12345",
  "reason": "Document the temporary mitigation and why upgrade is blocked",
  "owner": "team-or-person-accountable",
  "expires_on": "2026-12-01"
}
```

Use the actual package and vulnerability identifiers from the scan. Choose the shortest reasonable expiry, track a remediation issue, and remove the exception when remediation is complete. The example values above are illustrative, not an approved exception.

## Limitations

This gate audits Python packages visible to `pip-audit`. It does not replace OS/container image scanning, source-code analysis, secret scanning, threat modeling, or a full security assessment. Severity enrichment and additional ecosystem scanners should be added as separate, independently verified capabilities rather than guessed from missing metadata.

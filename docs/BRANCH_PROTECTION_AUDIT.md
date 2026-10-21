# Main branch protection audit

The weekly/manual `SAQA Main Branch Protection Audit` reads the actual GitHub protection response for `main` and compares it with `security/branch-protection-policy.json`. It checks that strict required status checks are enabled, every configured required context is present and bound to the GitHub Actions app, and force-push/deletion exceptions are disabled.

## Permission setup

Create a repository secret named `SAQA_REPO_ADMIN_AUDIT_TOKEN` from a fine-grained token restricted to this repository with **Administration: read-only** permission. Give it a short, controlled expiry and rotate it per your security policy. The token is only passed to `gh api` at runtime; the token itself is not written to reports or artifacts. The workflow intentionally has no `pull_request` trigger.

After setting the secret, manually run **SAQA Main Branch Protection Audit** from GitHub Actions. The same audit runs weekly. If the token is absent, expired, or lacks permission, the artifact records `UNVERIFIED`; it does not imply that protection is enabled or disabled. The workflow itself fails closed for both `UNVERIFIED` and `FAIL` after preserving the report artifact, so a scheduled run cannot appear green when the settings were not actually checked. An API response showing missing or incorrect protections results in `FAIL`.

## Required checks

The checked-in policy lists the stable status-check names from current SAQA CI, contract, accessibility, mobile, performance, framework-integrity, Advanced QE, and container-scan jobs. Review the list whenever workflows or job names change. Branch protection must be configured in repository settings; the audit is read-only and does not edit branch settings or itself enforce merges.

## Important limits

A passing audit is a settings snapshot, not proof that every user, app, deploy key, ruleset, or out-of-band administrator cannot bypass policy. Keep administrator enforcement and review requirements under owner control, and re-run the audit after settings or workflow changes. Do not make direct changes to the checked-in policy just to accommodate weaker settings; update it only as part of an approved governance change.

# Jira CI integration

SAQA uses Jira as a QA control plane. The integration has two separate responsibilities:

1. **Bootstrap** — manually creates the nine stable QA work items when they do not exist.
2. **Continuous synchronization** — automatically writes verified GitHub Actions results back to QA-1 through QA-9.

## Required GitHub Actions secret

Create a repository secret named `JIRA_API_TOKEN`. The token is never stored in source code, artifacts, or test evidence.

## Runtime configuration

- `JIRA_BASE_URL=https://dreamedx.atlassian.net`
- `JIRA_EMAIL=teukusaiful7@gmail.com`
- `JIRA_PROJECT_KEY=QA`
- `JIRA_API_TOKEN` comes only from GitHub Actions Secrets

## Automated synchronization

`.github/workflows/jira-qa-automation.yml` listens for completed:

- `SAQA CI`
- `SAQA Accessibility`
- `SAQA Mobile Readiness`

The sync collects the exact workflow run, job conclusions, commit SHA, branch, and run URL. It then updates the mapped Jira QA work item with:

- deterministic PASS / FAIL / BLOCKED / PENDING / UNVERIFIED label;
- an idempotent ADF comment containing the exact CI run and commit;
- an available Jira workflow transition, only when Jira exposes an exact matching transition;
- a certification aggregate on QA-9.

The automation is **fail-closed**: missing GitHub evidence is never converted into PASS.

## Jira work-item mapping

| Jira | Control plane responsibility |
|---|---|
| QA-1 | Test Management Foundation / sync health |
| QA-2 | Web E2E Automation |
| QA-3 | Cross-Browser Matrix |
| QA-4 | API Quality Gate |
| QA-5 | Security Regression Gate |
| QA-6 | Accessibility Gate |
| QA-7 | Performance Quality Gate |
| QA-8 | Evidence & Allure Traceability |
| QA-9 | Certification Readiness |

## Activation requirement

The continuous sync uses GitHub's `workflow_run` event. GitHub requires a `workflow_run` workflow file to exist on the repository's default branch before that trigger can execute. Therefore this feature becomes active after the Jira automation changes are merged into `main`.

The privileged sync workflow checks out only trusted `main` and never executes triggering branch/PR code. It requests only GitHub `actions: read` and `contents: read` permissions.

## Bootstrap

`jira-integration.yml` is now manual-only. Use it only to create missing QA work items or verify Jira access; continuous CI result updates belong to `jira-qa-automation.yml`.

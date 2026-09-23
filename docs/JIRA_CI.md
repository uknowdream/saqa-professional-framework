# Jira CI integration

SAQA uses Jira as a QA control plane. The integration now covers event-driven synchronization, deterministic defect creation, release certification, and recovery reconciliation.

## Responsibilities

1. **Bootstrap** — manually creates the nine stable QA work items when they do not exist.
2. **Continuous synchronization** — automatically writes verified GitHub Actions results back to QA-1 through QA-9.
3. **Defect automation** — a verified FAIL creates one deterministic Jira Bug per domain/run; repeated delivery never duplicates the Bug.
4. **Release certification** — certification is granted only when all mandatory quality workflows have verified PASS evidence.
5. **Nightly reconciliation** — missed events and Jira state drift are repaired from the latest completed `main` evidence.

## Required GitHub Actions secret

Create a repository secret named `JIRA_API_TOKEN`. The token is never stored in source code, artifacts, or test evidence.

## Runtime configuration

- `JIRA_BASE_URL=https://dreamedx.atlassian.net`
- `JIRA_EMAIL` is the Jira automation account email configured by the repository owner.
- `JIRA_PROJECT_KEY=QA`
- `JIRA_API_TOKEN` comes only from GitHub Actions Secrets

## Automated synchronization

`.github/workflows/jira-qa-automation.yml` listens for completed:

- `SAQA CI`
- `SAQA Contract Testing`
- `SAQA Accessibility`
- `SAQA Mobile Readiness`

The sync collects the exact workflow run, job conclusions, commit SHA, branch, and run URL. It then updates the mapped Jira QA work item with:

- deterministic PASS / FAIL / BLOCKED / PENDING / UNVERIFIED label;
- an idempotent ADF comment containing the exact CI run and commit;
- an available Jira workflow transition, only when Jira exposes an exact matching transition;
- a certification aggregate on QA-9;
- a deterministic Jira Bug when a verified domain result is FAIL.

The automation is **fail-closed**: missing GitHub evidence is never converted into PASS.

## Automatic defect lifecycle

```text
Verified CI FAIL
      ↓
Jira QA control item = FAIL
      ↓
Deterministic Bug created once
      ↓
Developer fixes code
      ↓
New commit
      ↓
Full qualifying CI
      ↓
PASS / FAIL evidence
      ↓
Jira control state reconciled
```

A Bug summary contains the managed QA issue, workflow, and immutable run ID so retries are idempotent.

## Release certification

`.github/workflows/qa-release-certification.yml` waits until all four mandatory workflows have completed for the exact commit, then evaluates `scripts/qa_release_gate.py`.

Certification rules:

- `CERTIFIED` only when `SAQA CI`, `SAQA Contract Testing`, `SAQA Accessibility`, and `SAQA Mobile Readiness` are all PASS;
- `FAIL`, `BLOCKED`, `PENDING`, missing, or `UNVERIFIED` evidence means `NOT_CERTIFIED`;
- the decision and exact workflow evidence are emitted as `artifacts/release-certification.json`.

## Nightly reconciliation

`.github/workflows/jira-nightly-reconciliation.yml` runs daily and can also be started manually. It finds the latest completed run on `main` for each mandatory workflow and reuses the same idempotent synchronization engine. This provides recovery from missed `workflow_run` delivery and detects/reduces Jira state drift.

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
| QA-9 | Certification Readiness / aggregate gate |

## Security model

The privileged Jira workflows check out only trusted `main` and never execute triggering branch/PR code. They request only GitHub `actions: read` and `contents: read` permissions. Jira credentials are provided only at runtime from GitHub Actions Secrets.

## Activation requirement

The event-driven Jira sync and release certification use GitHub's `workflow_run` event. GitHub requires these workflow files to exist on the repository's default branch before those triggers can execute. Therefore merge the automation changes into `main` before expecting automatic post-CI synchronization.

## Bootstrap

`jira-integration.yml` is manual-only. Use it to create missing QA work items or verify Jira access; continuous result updates belong to the event-driven sync and nightly reconciliation workflows.

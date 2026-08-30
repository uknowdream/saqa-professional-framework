# SAQA User Manual

## Purpose

SAQA is an evidence-driven QA automation platform. It is intended to make test execution, diagnostics, reporting, and certification reproducible and auditable.

## Standard workflow

```text
Define scope
  ↓
Select authorized target
  ↓
Configure environment
  ↓
Run capability suites
  ↓
Collect evidence
  ↓
Review failures/blockers
  ↓
Generate report
  ↓
Certification gate
```

## Target selection

For learning and framework validation, prefer local/containerized OWASP Juice Shop and OWASP WebGoat. Use ReqRes for safe API integration where appropriate, preferably self-hosted when network independence is important.

Never test an application without authorization. Never use destructive actions simply to manufacture a failure or a PASS.

## Configuration checklist

Before a target run, verify:

- target URL is correct;
- test account is authorized;
- test data is disposable or approved;
- API base URL is correct;
- database access is read-only where possible;
- required browser binaries are installed;
- Docker is available when using containerized targets;
- secrets are supplied through environment variables or CI secrets;
- Jira/Allure integrations are configured only when required.

## Running QA

Start with the smallest relevant suite. After a framework change, run the affected tests first and then the full regression suite.

For cross-browser validation, execute one browser per CI matrix job so a browser failure is attributable to the correct runtime.

For performance testing, use explicit thresholds and a controlled environment. Do not interpret a local laboratory latency measurement as a production capacity claim.

## Reading results

### PASS
The test executed successfully and generated sufficient evidence.

### FAIL
The test executed but an assertion or quality gate failed. Investigate the application, environment, data, or test implementation.

### BLOCKED
The test could not execute because a prerequisite was unavailable. Examples include missing browser binaries, Docker daemon, credentials, target URL, or external network access.

### UNVERIFIED
The available evidence is insufficient to establish a result. Do not promote it to PASS.

## Defect handling

A useful defect report contains:

1. title;
2. severity/priority;
3. target and environment;
4. preconditions;
5. reproduction steps;
6. expected result;
7. actual result;
8. evidence;
9. correlation/run ID;
10. suspected component, if known.

Jira integration should create/update defects only after the automation result has been validated. Credentials must remain outside source control.

## Allure

Allure is the human-readable reporting layer. Raw machine evidence remains authoritative; a rendered report must not be treated as proof if its source evidence is stale or missing.

## Certification

Certification is capability-based. A full certification requires every mandatory capability to have fresh evidence and no unresolved mandatory FAIL/BLOCKED/UNVERIFIED state.

Deliberately vulnerable benchmarks require special classification: an expected vulnerability is a benchmark finding, while an unexpected regression in the SAQA system remains a defect.

## Maintenance

After changing selectors, API contracts, fixtures, dependencies, configuration, or certification rules:

```text
Change
 ↓
Targeted test
 ↓
Full regression
 ↓
Evidence validation
 ↓
Certification
```

Document every new capability in the same change that introduces it.

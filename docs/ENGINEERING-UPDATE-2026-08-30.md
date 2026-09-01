# SAQA Engineering Update — 2026-08-30

## Purpose

This commit establishes the engineering-update trail for the SAQA Professional QA Automation Framework. It does not claim production certification or fabricate test execution.

## Validation policy

- PASS requires fresh, verifiable execution evidence.
- FAIL means the test executed and failed.
- BLOCKED means execution is prevented by an environment, dependency, credential, or infrastructure prerequisite.
- UNVERIFIED means evidence is insufficient to determine the result.
- NOT_APPLICABLE is used only when a capability is genuinely outside the target scope.

## Target strategy

Primary reproducible security/full-stack targets:

- OWASP Juice Shop, preferably deployed locally/containerized.
- OWASP WebGoat, preferably deployed locally/containerized.

Secondary API integration target:

- ReqRes Agent Sandbox, with self-hosting preferred for deterministic certification.

NeoCapture is explicitly excluded from the SAQA target registry.

## Engineering priorities

1. Reproducible Node dependencies and lockfile.
2. Web/API/DB automation.
3. Chromium/Firefox/WebKit matrix with one browser per CI matrix job.
4. Mobile-web and native-mobile readiness.
5. Accessibility.
6. Security and safe adversarial validation against authorized/local targets.
7. Performance and reliability.
8. Docker reproducibility.
9. GitHub Actions CI/CD.
10. Allure/Jira integration.
11. Evidence integrity and anti-tampering controls.
12. Flaky-test detection.
13. Capability-level certification.

## Certification principle

A deliberately vulnerable benchmark must distinguish expected benchmark vulnerabilities from unexpected vulnerabilities in a normal application. Remote targets are secondary evidence; local/containerized targets are preferred for authoritative certification.

## Current repository note

The repository is being incrementally upgraded from its existing baseline. This update intentionally records the engineering direction without claiming that absent framework components have already been implemented.

## Next execution gate

The next authoritative CI run should verify dependency installation, browser provisioning, Docker runtime, local Juice Shop/WebGoat execution, evidence generation, adversarial evidence checks, and certification gates.

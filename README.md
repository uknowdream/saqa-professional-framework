# SAQA Professional QA Automation Framework

**SAQA** is an evidence-driven QA automation framework designed for Web, API, Database, Security, Accessibility, Performance, Mobile readiness, Cross-Browser, CI/CD, Allure/Jira integration, adversarial validation, flaky-test detection, and certification.

> **Certification rule:** never treat BLOCKED or UNVERIFIED as PASS. Certification is based on fresh, reproducible evidence.

## Quick Start

### Requirements

- Python 3.11+
- Node.js 20+ for the browser/API layer
- Git
- Docker (recommended for reproducible security targets)
- Playwright browsers for cross-browser execution

### Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
```

On Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
pip install -e '.[test]'
```

### Run the self-check

```bash
pytest -q
```

The self-check validates framework behavior and certification/evidence rules. It is not a claim that external browsers, Docker, mobile devices, Jira, or a real application target are available.

## API Validation

SAQA includes a dependency-light HTTP validation layer for deterministic API checks:

```python
from saqa.api import assert_json_fields, request

response = request('http://127.0.0.1:3000/api/Products/1')
assert response.status_code == 200
assert_json_fields(response, ('id', 'name'))
```

The API client records status code, headers, response body, elapsed time, and transport errors. It does not automatically retry non-idempotent methods.

## Recommended Target Strategy

Use reproducible, authorized targets for authoritative certification:

- **OWASP Juice Shop** — primary Web/API/Security benchmark; deploy locally or in Docker.
- **OWASP WebGoat** — Java/Spring security benchmark; deploy locally or in Docker.
- **ReqRes Agent Sandbox** — API reliability and deterministic failure scenarios; self-host when authoritative offline certification is required.

**NeoCapture is not a SAQA test target.**

## Capability Model

SAQA reports each capability independently:

| Capability | Purpose |
|---|---|
| Web | UI workflows, locators, forms, navigation |
| API | HTTP contracts, schema, auth, negative cases |
| Database | data integrity and persistence validation |
| Security | safe authorized security checks |
| Accessibility | WCAG-oriented automated checks |
| Performance | latency, throughput and regression thresholds |
| Cross-Browser | Chromium, Firefox and WebKit |
| Mobile | responsive/mobile-web and native readiness |
| Reliability | retries, concurrency and failure handling |
| Evidence | immutable/tamper-evident execution evidence |
| CI/CD | reproducible pipeline execution |
| Allure | human-readable test reporting |
| Jira | defect lifecycle integration |
| Certification | fail-closed quality gates |

## Result Semantics

- **PASS** — fresh execution produced sufficient evidence.
- **FAIL** — test executed and failed.
- **BLOCKED** — execution could not proceed because of an environment, dependency, credential, target, or infrastructure prerequisite.
- **UNVERIFIED** — evidence is insufficient to determine the result.
- **N/A** — capability is genuinely outside the declared scope.

A certification gate must fail closed when mandatory evidence is missing, stale, incomplete, or tampered with.

## Documentation

Full user and engineering documentation lives under `docs/`:

- `GETTING-STARTED.md` — installation and first run
- `USER-MANUAL.md` — complete user workflow
- `QA-MANUAL.md` — QA execution methodology
- `ARCHITECTURE.md` — framework architecture
- `CONFIGURATION.md` — configuration reference
- `TESTING-GUIDE.md` — writing and organizing tests
- `WEB-TESTING.md` — web automation
- `API-TESTING.md` — API automation
- `DATABASE-TESTING.md` — database validation
- `SECURITY-TESTING.md` — authorized security testing
- `ACCESSIBILITY.md` — accessibility automation
- `PERFORMANCE.md` — performance testing
- `MOBILE-TESTING.md` — mobile readiness
- `CROSS-BROWSER.md` — browser matrix
- `DOCKER.md` — reproducible target containers
- `CI-CD.md` — GitHub Actions
- `ALLURE.md` — reporting
- `JIRA.md` — defect integration
- `EVIDENCE.md` — evidence integrity
- `FLAKY-TESTING.md` — flaky detection
- `SECURITY-BENCHMARKS.md` — Juice Shop/WebGoat
- `CERTIFICATION.md` — quality gates
- `TROUBLESHOOTING.md` — diagnostics
- `FAQ.md` — common questions

## Engineering Workflow

```text
Audit → Branch → Implement → Test → Commit → PR → CI → Fix → Regression → Certification
```

Do not merge a change merely because the source compiles. The relevant tests and evidence must be reproducible.

## Security Boundary

Security automation is restricted to targets that are explicitly authorized, locally/container deployed, or otherwise approved for testing. Do not run destructive exploitation against arbitrary public systems.

## Development Principles

1. Evidence before claims.
2. Fail closed.
3. Reproducible dependencies.
4. Small, reviewable commits.
5. Documentation ships with features.
6. External infrastructure failures are reported separately from application failures.
7. Expected vulnerabilities in deliberately vulnerable benchmarks are classified as benchmark findings, not automatically as framework defects.

## Status

This repository is under active engineering. A capability is certified only when the corresponding fresh execution evidence exists in the current environment/CI run.

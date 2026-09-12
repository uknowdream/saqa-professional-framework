# SAQA Professional Framework 🚀

> A production-minded **QA Automation Engineering framework** for Web, API, Mobile readiness, CI/CD quality gates, evidence integrity, and release certification.

[![QA Automation](https://img.shields.io/badge/QA-Automation-blue)](#capabilities) [![Playwright](https://img.shields.io/badge/Playwright-Web%20%26%20API-2ead33)](#web--api-automation) [![BDD](https://img.shields.io/badge/BDD-Gherkin-purple)](#bdd--gherkin) [![CI%2FCD](https://img.shields.io/badge/CI%2FCD-GitHub%20Actions-black)](#cicd) [![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## ⭐ Why this project?

SAQA is designed as a practical reference architecture for QA engineers moving from manual testing toward **professional automation and quality engineering**.

The framework treats automation as an engineering system: tests produce reproducible results, evidence is preserved, quality gates are explicit, and certification must never succeed without sufficient evidence.

## 🧩 Capabilities

| Area | Coverage |
|---|---|
| Web Automation | Playwright, selectors, fixtures, POM, E2E smoke/regression |
| API Testing | REST, status codes, headers, JSON, schema, response-time gates |
| Mobile Readiness | Browser/device-oriented readiness matrix and canonical evidence |
| Accessibility | Read-only accessibility readiness checks and browser matrix |
| Performance | Deterministic response-time/performance gates |
| Security | Target authorization, dependency/secret hygiene, safe regression foundations |
| Docker | Reproducible local/containerized authorized targets |
| BDD | Gherkin feature/scenario structure |
| Evidence | JSON evidence, SHA-256 manifests, canonical aggregation |
| CI/CD | GitHub Actions multi-browser quality gates |
| Jira | Project access/bootstrap and integration foundation |
| Certification | Evidence-based certification semantics |

## 🏗️ Target Architecture

```text
SAQA Professional Framework
│
├── Web Automation
│   ├── Page Object Model
│   ├── Fixtures
│   ├── Test Data
│   └── UI Assertions
│
├── API Automation
│   ├── Request Clients
│   ├── Contract Validation
│   ├── Schema Validation
│   └── Performance Assertions
│
├── Mobile Readiness
│   └── Cross-browser/device-oriented checks
│
├── Accessibility
│   └── Read-only browser accessibility gates
│
├── BDD
│   └── Gherkin Features
│
├── Evidence
│   ├── Execution JSON
│   ├── Canonical manifests
│   └── SHA-256 integrity verification
│
├── Integrations
│   ├── Jira
│   └── Allure-compatible reporting architecture
│
└── CI/CD
    └── GitHub Actions
```

## 🚀 Quick Start Tutorial

### 1. Prerequisites

Recommended local tooling:

- Python **3.11+**
- Git
- Docker Engine/Desktop
- Playwright-compatible browser dependencies
- Optional: Node.js when using additional JavaScript-based tooling

Clone the repository and enter it:

```bash
git clone https://github.com/uknowdream/saqa-professional-framework.git
cd saqa-professional-framework
```

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it on Linux/macOS:

```bash
source .venv/bin/activate
```

Activate it on Windows PowerShell:

```powershell
.venv\\Scripts\\Activate.ps1
```

Install the project and test dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
```

### 2. Run the framework unit/regression suite

```bash
python -m pytest
```

With coverage:

```bash
python -m pytest --cov=saqa --cov-report=term-missing
```

### 3. Run safe Juice Shop Web E2E locally

SAQA uses a reproducible local OWASP Juice Shop container for reference testing.

Start the authorized local target:

```bash
docker run --detach --rm --name saqa-juice-shop -p 127.0.0.1:3000:3000 bkimminich/juice-shop:v20.2.0
```

Install Playwright and the browser you want:

```bash
python -m pip install "playwright>=1.50,<2"
python -m playwright install chromium
```

Run the read-only E2E smoke:

```bash
python scripts/juice_shop_e2e.py
```

For another browser:

```bash
SAQA_BROWSER=firefox python scripts/juice_shop_e2e.py
SAQA_BROWSER=webkit python scripts/juice_shop_e2e.py
```

Stop the local target when finished:

```bash
docker stop saqa-juice-shop
```

### 4. Run the Juice Shop API smoke

Start the same local target if it is not running, then execute:

```bash
python scripts/juice_shop_api_smoke.py
```

The reference API test is GET-only and validates HTTP status, JSON structure, and a response-time budget. Evidence is written under `artifacts/targets/`.

### 5. Run the accessibility readiness gate

Start Juice Shop on `127.0.0.1:3000`, install the selected Playwright browser, then:

```bash
SAQA_BROWSER=chromium python scripts/juice_shop_accessibility_gate.py
SAQA_BROWSER=firefox python scripts/juice_shop_accessibility_gate.py
SAQA_BROWSER=webkit python scripts/juice_shop_accessibility_gate.py
```

The gate is intentionally restricted to local HTTP loopback targets and performs read-only browser validation. A failure must be investigated; do **not** weaken the assertion simply to obtain a green build.

### 6. Understand evidence

Typical evidence contains:

```text
schema
test_id
status
target
browser
http_methods
destructive_actions
observed_at
details
```

A professional result must be traceable to the target, execution, environment, and evidence. Canonical aggregation verifies the evidence manifest before it is accepted.

### 7. Run the framework in CI

Recommended execution order:

```text
Static / compile checks
        ↓
Unit / regression tests
        ↓
API smoke
        ↓
Web E2E
        ↓
Performance
        ↓
Accessibility
        ↓
Cross-browser / mobile readiness
        ↓
Evidence aggregation
        ↓
Quality gate
        ↓
Certification decision
```

GitHub Actions performs the authoritative CI execution. Do not interpret a queued or in-progress job as PASS.

## 🔐 Safety Rules

SAQA reference targets are authorized, reproducible, and local/containerized whenever possible.

**Allowed reference targets:**

- Local/containerized OWASP Juice Shop
- Local/containerized OWASP WebGoat
- Other explicitly authorized safe API targets

**Never:**

- point the reference tests at an unauthorized third-party system;
- run destructive POST/PUT/PATCH/DELETE scenarios against reference targets unless a dedicated isolated fixture explicitly requires them;
- place credentials, API tokens, passwords, or private keys in source code or test artifacts;
- convert a genuine quality failure into a PASS by weakening or bypassing the assertion.

## 🚦 Quality Strategy

SAQA treats automation as an engineering system rather than a collection of scripts.

### Test pyramid

```text
              /\\
             /E2E\\          Small number
            /----\\
           / API  \\         Fast feedback
          /--------\\
         /   Unit   \\       Large coverage
        /------------\\
```

Recommended execution order:

1. Static checks
2. Unit/component checks
3. API tests
4. Web smoke tests
5. Regression suite
6. Cross-browser / mobile flows
7. Accessibility / performance / security gates
8. Evidence aggregation
9. Release certification

## 🌐 Web & API Automation

The framework supports Playwright-based automation with reusable fixtures and Page Object Model design.

Example structure:

```text
src/
├── pages/
├── fixtures/
├── api/
├── utils/
├── data/
└── tests/
    ├── smoke/
    ├── regression/
    └── api/
```

## 🧪 Test Design Techniques

SAQA incorporates classic black-box techniques before automation begins:

- **Equivalence Partitioning** — reduce redundant input combinations.
- **Boundary Value Analysis** — target values around limits.
- **Decision Tables** — validate complex business rules.
- **State Transition** — validate behavior across application states.
- **Error Guessing** — target failure-prone scenarios using engineering experience.

Automation should encode meaningful risk coverage — not simply maximize the number of scripts.

## 🔌 API Validation Checklist

For REST APIs, validate at minimum:

- HTTP status code
- Response body
- Required fields
- Data types
- JSON schema / contract
- Headers
- Authentication / authorization behavior
- Error response structure
- Response time
- Negative scenarios
- Boundary conditions

## 📱 Mobile Automation / Readiness

Mobile-oriented scenarios can be organized around Maestro-style declarative flows:

```text
mobile/
├── login.yaml
├── checkout.yaml
├── profile.yaml
└── regression/
```

The current reference CI also validates mobile-oriented readiness across Chromium, Firefox, and WebKit and aggregates its evidence.

## ♿ Accessibility

Accessibility is treated as a quality gate, not as a cosmetic check.

Current readiness checks include:

- document language
- document title
- rendered image `alt` presence
- accessible-name candidates for interactive controls
- headings
- landmarks
- control-level diagnostic evidence

The current gate is a **readiness heuristic**, not a claim of complete WCAG conformance. For certification-grade WCAG assessment, use an independent accessibility oracle such as axe-core and correlate its findings with SAQA evidence.

## 🧠 BDD / Gherkin

Example:

```gherkin
Feature: User login

  Scenario: Login with valid credentials
    Given the user is on the login page
    When the user enters valid credentials
    And submits the login form
    Then the dashboard should be displayed
```

BDD communicates behavior and acceptance criteria; it does not replace sound test design.

## 📊 Reporting & Evidence

A professional execution should answer:

- What was tested?
- What passed?
- What failed?
- Which environment was used?
- What evidence proves the result?
- Which defect or requirement is affected?

SAQA uses structured evidence and canonical manifests with SHA-256 integrity verification. Individual failure artifacts should be preserved even when a quality gate fails.

## ⚙️ CI/CD Quality Gate

A mature pipeline should fail when critical quality conditions are not met.

```text
Push / Pull Request
        ↓
Static Validation
        ↓
Unit / API / Web
        ↓
Cross-browser / Mobile
        ↓
Accessibility / Performance / Security
        ↓
Evidence Aggregation
        ↓
Quality Gate
        ↓
Certification
```

### GitHub Actions

The CI uses explicit authorized targets and browser matrices. Important statuses are:

- `PASS` — verified successful execution
- `FAIL` — verified quality or framework failure
- `BLOCKED` — cannot proceed because a required dependency is unavailable
- `UNVERIFIED` — implementation/evidence is insufficient to make a claim
- `N/A` — intentionally not applicable

Never treat `QUEUED` or `IN_PROGRESS` as PASS.

## 🧾 Certification Rules

Certification follows a fail-closed principle:

```text
No evidence
     ↓
UNVERIFIED
     ↓
NOT CERTIFIED
```

Likewise, a mandatory capability with FAIL, BLOCKED, or UNVERIFIED evidence cannot produce a certification PASS.

This prevents false release certification caused by missing evidence.

## 🔗 Jira / Allure Integration

Jira integration provides the foundation for project access and bootstrap work items. The intended traceability chain is:

```text
Test Case
   ↓
Executor
   ↓
Result
   ↓
Evidence
   ↓
Defect / Requirement
   ↓
Jira / Allure
   ↓
Release Certification
```

Do not place Jira tokens or credentials in README files, source code, commits, or test artifacts. Store secrets in the CI secret manager.

## 🐳 Docker Targets

Reference target images:

```text
OWASP Juice Shop: bkimminich/juice-shop:v20.2.0
OWASP WebGoat:    webgoat/webgoat:2026
```

Use loopback bindings for local testing whenever possible. Pinning versions makes runs reproducible and makes evidence easier to audit.

## 🧪 Flaky-Test Engineering

A mature implementation should distinguish:

```text
PASS → PASS → PASS
        = stable PASS

PASS → FAIL → PASS
        = flaky candidate

FAIL → FAIL → FAIL
        = stable failure
```

Flaky detection must not silently hide failures. A quarantined test should remain visible and traceable with its reason and history.

## 🛡️ Safe Adversarial Testing

Adversarial testing should be performed only against isolated authorized targets such as local Juice Shop/WebGoat containers.

Useful safe categories include:

- malformed input handling
- boundary values
- invalid JSON/API contract cases
- missing/extra fields
- unexpected state transitions
- safe header/configuration checks
- resilience and deterministic retry behavior

Do not turn the framework into an unrestricted external scanner.

## 🗺️ Roadmap

- [x] Professional QA automation architecture
- [x] Web automation direction
- [x] API testing direction
- [x] Mobile readiness matrix
- [x] BDD / Gherkin guidance
- [x] Docker reference targets
- [x] Multi-browser CI matrices
- [x] Performance quality gate
- [x] Accessibility readiness gate
- [x] Canonical evidence aggregation
- [x] Evidence integrity verification
- [x] Certification fail-closed semantics
- [x] Jira integration foundation
- [ ] Independent axe-core accessibility oracle
- [ ] Database quality gate
- [ ] Advanced application security regression
- [ ] Advanced API contract/property testing
- [ ] Flaky-test intelligence
- [ ] Unified failure classification
- [ ] Full Allure execution/evidence lifecycle
- [ ] Full Jira execution/result/defect/evidence lifecycle
- [ ] Final multi-domain certification release gate

## 📦 Included Reference Package

The repository currently includes the packaged framework reference:

**`SAQA-Professional-Framework-v1.1.zip`**

Use the documentation in this repository as the architectural guide and the ZIP package as the bundled reference artifact.

## 🤝 Contributing

Contributions, suggestions, bug reports, and real-world QA use cases are welcome.

Please read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.

## 📄 License

MIT License — see [LICENSE](LICENSE).

## 👨‍💻 Author

**T. Saiful Bahri**  
Quality Assurance Engineer | Software Engineer

If this framework helps your QA journey, consider giving the repository a ⭐ and sharing it with another QA engineer.

---

### ⭐ Starstruck goal

This project is intentionally being developed as a genuinely useful open-source QA resource. GitHub's Starstruck achievement is triggered when a repository created by the account reaches the required star milestone; the first published milestone is **16 stars on a single repository**.

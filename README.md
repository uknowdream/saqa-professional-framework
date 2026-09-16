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
| Accessibility | Read-only accessibility readiness checks, axe-core oracle, browser matrix |
| Performance | Deterministic response-time/performance gates |
| Security | Target authorization, dependency/secret hygiene, safe regression foundations |
| Database | Isolated SQLite constraint, FK, aggregation, parameterization and rollback gate |
| Docker | Reproducible local/containerized authorized targets |
| BDD | Gherkin feature/scenario structure |
| Evidence | JSON evidence, SHA-256 manifests, canonical aggregation |
| CI/CD | GitHub Actions multi-browser quality gates |
| Jira | Project access/bootstrap and integration foundation |
| Certification | Evidence-based certification semantics |

## 🚀 Quick Start Tutorial

### 1. Prerequisites

- Python **3.11+**
- Git
- Docker Engine/Desktop
- Playwright-compatible browser dependencies
- Optional Node.js for additional JavaScript tooling

```bash
git clone https://github.com/uknowdream/saqa-professional-framework.git
cd saqa-professional-framework
python -m venv .venv
```

Linux/macOS:

```bash
source .venv/bin/activate
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Install the framework and test dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
```

### 2. Run unit/regression tests

```bash
python -m pytest
python -m pytest --cov=saqa --cov-report=term-missing
```

### 3. Run safe Juice Shop Web E2E locally

Start the pinned local OWASP Juice Shop target:

```bash
docker run --detach --rm --name saqa-juice-shop -p 127.0.0.1:3000:3000 bkimminich/juice-shop:v20.2.0
```

Use the same Playwright version as CI for reproducibility:

```bash
python -m pip install "playwright==1.62.0"
python -m playwright install chromium
```

Run the read-only E2E smoke:

```bash
python scripts/juice_shop_e2e.py
```

Other browsers:

```bash
SAQA_BROWSER=firefox python scripts/juice_shop_e2e.py
SAQA_BROWSER=webkit python scripts/juice_shop_e2e.py
```

Stop the target:

```bash
docker stop saqa-juice-shop
```

### 4. Run the Juice Shop API smoke

With the same local target running:

```bash
python scripts/juice_shop_api_smoke.py
```

The reference API check is GET-only and validates status, JSON structure, and response-time budget. Evidence is written under `artifacts/targets/`.

### 5. Run the database quality gate

The database gate is deliberately isolated: it uses SQLite `:memory:` only and does not touch an external or persistent database.

```bash
python scripts/database_quality_gate.py
```

The gate validates:

- foreign-key enforcement;
- `PRIMARY KEY`, `UNIQUE`, `NOT NULL`, and `CHECK` constraints;
- parameterized SQL access;
- deterministic aggregation;
- transaction rollback behavior;
- savepoint isolation for expected constraint failures.

Successful evidence is emitted to:

```text
artifacts/targets/database-quality.json
```

The constraint probes use savepoints so an expected `IntegrityError` cannot roll back unrelated fixture state. The regression suite also verifies that this isolation preserves previously inserted rows.

### 6. Run the accessibility readiness gate

Start Juice Shop on `127.0.0.1:3000`. The CI workflow installs Node.js 22, pinned axe-core `4.10.2`, and pinned Playwright `1.62.0` before running the gate.

For local execution, install the same oracle dependency and browser:

```bash
npm install --no-save --ignore-scripts "axe-core@4.10.2"
python -m pip install "playwright==1.62.0"
python -m playwright install chromium
```

Then:

```bash
SAQA_BROWSER=chromium SAQA_AXE_CORE_PATH=node_modules/axe-core/axe.min.js python scripts/juice_shop_accessibility_gate.py
SAQA_BROWSER=firefox SAQA_AXE_CORE_PATH=node_modules/axe-core/axe.min.js python scripts/juice_shop_accessibility_gate.py
SAQA_BROWSER=webkit SAQA_AXE_CORE_PATH=node_modules/axe-core/axe.min.js python scripts/juice_shop_accessibility_gate.py
```

The gate is restricted to local HTTP loopback targets and performs read-only browser validation. The DOM heuristic is correlated with an independent axe-core oracle. An unnamed control without oracle confirmation remains `INCONCLUSIVE` and therefore fails closed; focusability alone is not treated as proof of a false positive. A failure must be investigated rather than weakened merely to obtain a green build.

### 7. Understand evidence

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

Canonical aggregation verifies evidence before acceptance. SHA-256 manifests provide tamper-evident integrity metadata for the collected JSON evidence.

## 🔐 Safety Rules

Reference targets are authorized, reproducible, and local/containerized whenever possible.

**Allowed reference targets:**

- Local/containerized OWASP Juice Shop
- Local/containerized OWASP WebGoat
- Other explicitly authorized safe API targets

**Never:**

- point reference tests at an unauthorized third-party system;
- run destructive POST/PUT/PATCH/DELETE scenarios against reference targets unless a dedicated isolated fixture explicitly requires them;
- place credentials, API tokens, passwords, or private keys in source code or test artifacts;
- convert a genuine quality failure into PASS by weakening or bypassing an assertion.

## 🚦 Quality Strategy

SAQA treats automation as an engineering system rather than a collection of scripts.

Recommended execution order:

1. Static checks
2. Unit/component checks
3. API tests
4. Web smoke tests
5. Regression suite
6. Cross-browser / mobile flows
7. Accessibility / performance / security / database gates
8. Evidence aggregation
9. Release certification

## 🌐 Web & API Automation

The framework supports Playwright-based automation with reusable fixtures and Page Object Model design.

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

Automation should encode meaningful risk coverage, not simply maximize script count.

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

Mobile-oriented scenarios can be organized around Maestro-style declarative flows. The current CI also validates mobile-oriented readiness across Chromium, Firefox, and WebKit and aggregates its evidence.

## ♿ Accessibility

Current readiness checks include document language/title, image `alt`, accessible-name candidates, headings, landmarks, and control-level diagnostics. An independent **axe-core 4.10.2** oracle runs the selected rules `aria-input-field-name`, `button-name`, `link-name`, and `label` across the browser matrix.

The framework keeps heuristic findings even when the oracle reports no violation. Classification is explicit:

- `NONE` — no heuristic finding;
- `CONFIRMED_ORACLE` — heuristic finding has independent oracle confirmation;
- `INCONCLUSIVE` — heuristic finding lacks independent oracle confirmation;
- future `FALSE_POSITIVE` decisions require explicit evidence beyond `tabindex` or focusability alone.

The gate is a **readiness assessment**, not a claim of complete WCAG conformance. Certification-grade assessment should expand oracle coverage and correlate additional accessibility-tree evidence.

## 🧠 BDD / Gherkin

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

Individual failure artifacts should be preserved even when a quality gate fails.

## ⚙️ CI/CD Quality Gate

```text
Push / Pull Request
        ↓
Static Validation
        ↓
Unit / API / Web
        ↓
Cross-browser / Mobile
        ↓
Accessibility / Performance / Security / Database
        ↓
Evidence Aggregation
        ↓
Quality Gate
        ↓
Certification
```

Important result semantics:

- `PASS` — verified successful execution
- `FAIL` — verified quality or framework failure
- `BLOCKED` — cannot proceed because a required dependency is unavailable
- `UNVERIFIED` — implementation/evidence is insufficient to make a claim
- `N/A` — intentionally not applicable

Never treat `QUEUED` or `IN_PROGRESS` as PASS.

## 🧾 Certification Rules

Certification is fail-closed:

```text
No evidence
     ↓
UNVERIFIED
     ↓
NOT CERTIFIED
```

A mandatory capability with FAIL, BLOCKED, or UNVERIFIED evidence cannot produce a certification PASS.

## 🔗 Jira / Allure Integration

The intended traceability chain is:

```text
Test Case → Executor → Result → Evidence → Defect / Requirement → Jira / Allure → Release Certification
```

Do not place Jira tokens or credentials in README files, source code, commits, or test artifacts. Store secrets in the CI secret manager.

## 🐳 Docker Targets

```text
OWASP Juice Shop: bkimminich/juice-shop:v20.2.0
OWASP WebGoat:    webgoat/webgoat:2026
```

Use loopback bindings for local testing whenever possible. Pin versions to improve reproducibility and auditability.

## 🧪 Flaky-Test Engineering

A mature implementation distinguishes stable PASS, flaky candidates, and stable failures. Flaky detection must never silently hide failures; quarantined tests remain visible and traceable with their reason and history.

## 🛡️ Safe Adversarial Testing

Useful safe categories on isolated authorized targets include malformed-input handling, boundary values, invalid API contract cases, missing/extra fields, unexpected state transitions, safe header/configuration checks, and deterministic retry/resilience behavior.

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
- [x] Independent axe-core accessibility oracle implementation
- [x] Database quality gate
- [x] Canonical evidence aggregation
- [x] Evidence integrity verification
- [x] Certification fail-closed semantics
- [x] Jira integration foundation
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

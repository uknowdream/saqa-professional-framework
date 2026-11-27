# SAQA Professional Framework 🚀

> A production-minded **QA Automation Engineering framework** for Web, API, Mobile readiness, CI/CD quality gates, evidence integrity, and release certification.

[![QA Automation](https://img.shields.io/badge/QA-Automation-blue)](#capabilities) [![Playwright](https://img.shields.io/badge/Playwright-Web%20%26%20API-2ead33)](#web--api-automation) [![BDD](https://img.shields.io/badge/BDD-Gherkin-purple)](#bdd--gherkin) [![CI%2FCD](https://img.shields.io/badge/CI%2FCD-GitHub%20Actions-black)](#cicd) [![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## ⭐ Why this project?

SAQA is designed as a practical reference architecture for QA engineers moving from manual testing toward **professional automation and quality engineering**.

The framework treats automation as an engineering system: tests produce reproducible results, evidence is preserved, quality gates are explicit, and certification must never succeed without sufficient evidence.

**Operations guide:** [SAQA User Manual](docs/USER_MANUAL.md) · [Getting Started](docs/GETTING_STARTED.md) · [Known Limitations](docs/KNOWN_LIMITATIONS.md) · [Branch Protection Audit](docs/BRANCH_PROTECTION_AUDIT.md)

## 🧩 Capabilities

| Area | Coverage |
|---|---|
| Web Automation | Playwright, selectors, fixtures, POM, E2E smoke/regression |
| API Testing | REST, status codes, headers, JSON, schema, response-time gates |
| Mobile Readiness | Browser/device-oriented readiness matrix and canonical evidence |
| Accessibility | Read-only accessibility readiness checks, axe-core oracle, browser matrix |
| Performance | Versioned k6 gates, repeated-run sample collection, metadata-bound baseline comparison |
| Security | Target authorization, dependency/secret hygiene, safe regression foundations |
| Database | Isolated SQLite constraint, FK, aggregation, parameterization and rollback gate |
| Docker | Reproducible local/containerized authorized targets |
| BDD | Gherkin feature/scenario structure |
| Evidence | JSON evidence, SHA-256 manifests, canonical aggregation |
| Test Stability | Advisory cross-run JUnit trends by Python version; same-commit variation signals and missing-artifact visibility |
| CI/CD | GitHub Actions multi-browser quality gates |
| Jira | Project access/bootstrap and integration foundation |
| Certification | Evidence-based certification semantics, release reports, commit-bound evidence history |

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
python -m playwright install chromium firefox webkit
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
python -m playwright install chromium firefox webkit
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

Current readiness checks include document language/title, image `alt`, accessible-name candidates, headings, landmarks, and control-level diagnostics. An independent **axe-core 4.10.2** oracle runs the selected rules `aria-input-field-name`, `button-name`, and `link-name` across the browser matrix.

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

Jira synchronization is fail-closed and evidence-driven. The trusted automation checks out `main`, rejects privileged synchronization for pull-request events, serializes Jira synchronization through a shared concurrency group, and ignores stale `main` workflow runs when their SHA is no longer the current `main` commit. Contract evidence is additionally bound to the exact workflow commit SHA before it can drive QA-4 classification. Nightly reconciliation downloads the same contract artifact for the selected common commit instead of silently falling back to workflow conclusion.


The intended traceability chain is:

```text
Test Case → Executor → Result → Evidence → Defect / Requirement → Jira / Allure → Release Certification
```

Do not place Jira tokens or credentials in README files, source code, commits, or test artifacts. Store secrets in the CI secret manager.

## 🐳 Docker Targets

```text
OWASP Juice Shop: bkimminich/juice-shop:v20.2.0
OWASP WebGoat:    webgoat/webgoat:v2026.4
```

Use loopback bindings for local testing whenever possible. Pin versions to improve reproducibility and auditability.

## 📈 Advanced QE Evidence

The advanced QE layer now produces Allure-compatible result files, append-only hash-chained quality history, deterministic property-style API cases, safe loopback security regression, deterministic retry/resilience checks, and a commit-bound release certification report. These controls remain fail-closed: generated artifacts do not override real test outcomes.

## 🧪 Flaky-Test Engineering

A mature implementation distinguishes stable PASS, flaky candidates, and stable failures. Flaky detection must never silently hide failures; quarantined tests remain visible and traceable with their reason and history.

## ⚡ SAQA CLI Command Center, Mobile APK/IPA Audit, PDF Certificate & Bilingual Jira (v2.6)

After installing the package (`pip install -e ".[test,lint]"`), you can drive end-to-end Web, API, Mobile App (`.apk`/`.aab`/`.ipa`), and Load/SLA QA workflows directly through the unified `saqa` CLI (or `python -m saqa`), including **100% pure Bahasa Indonesia (`--lang id`) and English (`--lang en`)** synchronization into Jira Cloud and **Executive PDF Sign-Off Reports (`qa-executive-report.pdf`)**:

```bash
# Check workstation readiness (Python version & optional runtimes)
saqa doctor

# 1. Audit a client Android (.apk/.aab) or iOS (.ipa) Mobile App & sync PDF/HTML/SARIF to Jira in Bahasa Indonesia:
saqa audit-mobile client-release.apk \
  --output-dir artifacts/mobile-id \
  --lang id \
  --sync-jira

# 2. Run a 9-pillar + SPA-Aware Multi-Page Crawler + Responsive Multi-Viewport Web Audit -> Jira (ID or EN):
saqa deep-audit https://www.dreamex.tech/ \
  --output-dir artifacts/deep-audit-id \
  --spa \
  --modern-security \
  --responsive \
  --crawl-pages 5 \
  --screenshot \
  --lang id \
  --sprint-start 2026-11-10 \
  --sprint-end 2026-12-01 \
  --sync-jira

# 3. Built-in Read-Only Concurrent HTTP Load & SLA Stress Gate (zero external k6 dependency):
saqa load-test http://127.0.0.1:3000/rest/products/search \
  --requests 50 \
  --concurrency 8 \
  --max-p95-ms 800 \
  --lang id \
  --output-dir artifacts/load-test

# 4. Switch Jira & reports seamlessly to English (--lang en) for international clients without duplicating tickets:
saqa sync-jira artifacts/deep-audit-id/evidence-manifest.json --lang en

# 5. Export Executive PDF Certificate, HTML, Markdown, JUnit XML, and SARIF v2.1.0:
saqa report artifacts/deep-audit-id/evidence-manifest.json \
  --lang id \
  --pdf artifacts/qa-executive-report.pdf \
  --html artifacts/report.html \
  --md artifacts/report.md \
  --junit artifacts/junit.xml \
  --sarif artifacts/results.sarif

# Multi-target head-to-head QA Benchmark Matrix (HTML, Markdown, CSV, JSON):
saqa benchmark https://www.dreamex.tech/ https://playwright.dev/ --output-dir artifacts/benchmark --spa

# Auto-generate or execute read-only contract tests directly from any OpenAPI 3.x / Swagger 2.0 spec:
saqa audit-openapi contracts/juice-shop.openapi.json --base-url http://127.0.0.1:3000 --lang id

# Verify tamper-evident evidence integrity, diff runs, & generate black-box test data:
saqa verify-manifest artifacts/deep-audit-id/evidence-manifest.json
saqa diff baseline-manifest.json artifacts/deep-audit-id/evidence-manifest.json --fail-on-regression
saqa generate-data pairwise --seed 42

# v2.7.0 Dual-Methodology SDLC (Agile Scrum/DoD vs Waterfall V-Model Stage-Gate & RTM):
# Waterfall mode (sequential non-overlapping Stage 1 -> Stage 2 -> Stage 3 Epics, RTM CSV, BAST Go/No-Go Sign-Off & Compressed PDF):
saqa deep-audit https://www.dreamex.tech/ --spa --modern-security --responsive --crawl-pages 5 --crawl-spa --screenshot --lang id --methodology waterfall --sprint-start 2026-11-10 --sprint-end 2026-12-01 --sync-jira

# Agile mode (Scrum Active Sprint sync, DoD checklist, dynamic Story Points & Defect SLA P0-P3):
saqa sync-jira artifacts/deep-audit/evidence-manifest.json --lang en --methodology agile
```

Key v2.7 modules under `src/saqa/`:

- **`saqa.methodology` & `saqa.jira_sync`** — Dual-methodology **Agile (Scrum/Kanban DoD, Story Points, P0–P3 SLA)** & **Waterfall (Sequential V-Model Stage 1–3 Exit Gates, Formal RTM `rtm-matrix.csv`, Release Sign-Off Certificate `release-signoff.md`)** engine with single-scan Jira Cloud sync, zero-duplicate cross-methodology/cross-language (`en`/`id`) Epics, Two-Way Waivers, and `429 Retry-After` attachment retry.
- **`saqa.ssrf` & `saqa.http_pool`** — Hop-by-hop Anti-SSRF redirect validation (blocks public-to-private/loopback/`169.254.169.254` redirects, strips `Authorization`/`Cookie` cross-origin), webhook IP guards + Telegram token redaction, and safe XML parsing blocking `<!DOCTYPE`/`<!ENTITY` XXE attacks.
- **`saqa.mobile_audit`** — Native Android (`.apk`/`.aab`) & iOS (`.ipa`/`.app.zip`) package auditor featuring a true struct-level **Android Binary XML (`AXML`, UTF-8 + UTF-16LE)** parser detecting binary `debuggable`, `usesCleartextTraffic`, `allowBackup`, unprotected `android:exported="true"` components, code signing, hardcoded secrets, 64-bit ABI, and optional Maestro E2E flows.
- **`saqa.web_audit` & `saqa.spa_audit`** — 9-Pillar Web/API/App-Link auditor (TLS, OWASP headers, WCAG 2.2 DOM + computed **WCAG 2.2 AA Color Contrast**, SEO/JSON-LD, parallel broken-link crawler, dotfile exposure, keep-alive performance, live SPA DOM + init-script `PerformanceObserver` Core Web Vitals `FCP`/`LCP`/`CLS`, CORS/SRI/`security.txt`/Android+iOS Universal Links/GraphQL introspection), Multi-Viewport Responsive Matrix, nested `<sitemapindex>` + SPA-rendered Multi-Page Crawler, and Declarative Browser UI Journeys.
- **`saqa.pdf_report`, `saqa.visual_diff` & `saqa.visual_evidence`** — Pure-Python ISO 32000 **FlateDecode-compressed** multi-page PDF executive UAT report (word-wrapping, page numbers, Agile/Waterfall Go/No-Go banner, HMAC-SHA256 provenance), PNG visual regression comparator with region masking & anti-aliasing tolerance, animation-frozen screenshots, PNG scorecards, SVG charts, and CSV matrices.
- **`saqa.load_test`, `saqa.reporting`, `saqa.runner` & `saqa.test_design`** — Bounded concurrent HTTP load/SLA tester, localized (`id`/`en`) HTML5/Markdown/JUnit XML/SARIF v2.1.0 exporters, chained/parallel HTTP runner, HMAC-SHA256 evidence manifests, and ISTQB BVA/EP/Pairwise/Decision-Table/State-Transition generators.

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
- [x] Serialized Jira synchronization and stale-main protection
- [x] Exact-SHA contract evidence provenance and nightly reconciliation
- [x] Local/containerized observability wiring (Prometheus → SAQA exporter → Grafana provisioning)
- [x] Advanced application-security regression on isolated authorized targets
- [x] Advanced API contract/property testing
- [x] Flaky-test intelligence with report-only quarantine telemetry
- [x] Unified failure classification and fail-closed certification semantics
- [x] Full Allure-compatible execution/evidence lifecycle
- [x] Full Jira execution/result/evidence control-plane integration
- [x] Final multi-domain certification release gate
- [x] Historical quality trend storage with tamper-evident hash chaining
- [x] Immutable release evidence index and artifact attestation
- [x] Cross-service test-data lifecycle management
- [x] Failure-path observability and preserved evidence

### Current engineering status

The framework has **40/40 roadmap controls implemented and verified in the current release baseline**. This is a roadmap-completion statement, not a claim of 100% code coverage. Release certification remains commit-specific and fail-closed: a release is certified only when fresh mandatory-domain evidence exists for the exact main commit and no mandatory control is FAIL, BLOCKED, UNVERIFIED, or PENDING.

### Supply-chain hardening

All GitHub Actions used by the framework are pinned to full 40-character commit SHAs and protected by a framework-integrity gate. This prevents a mutable action tag from silently changing the code executed by CI. Action pins should be updated through reviewed dependency updates rather than floating tags.

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

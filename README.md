# SAQA Professional Framework 🚀

> A production-minded **QA Automation Engineering framework** for Web, API, and Mobile quality assurance — built around reusable test architecture, CI/CD, reporting, and quality gates.

[![QA Automation](https://img.shields.io/badge/QA-Automation-blue)](#capabilities) [![Playwright](https://img.shields.io/badge/Playwright-Web%20%26%20API-2ead33)](#web--api-automation) [![BDD](https://img.shields.io/badge/BDD-Gherkin-purple)](#bdd--gherkin) [![CI%2FCD](https://img.shields.io/badge/CI%2FCD-GitHub%20Actions-black)](#cicd) [![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## ⭐ Why this project?

SAQA is designed as a practical reference architecture for QA engineers who want to move from manual testing toward **professional automation engineering**.

The framework focuses on:

- Web UI automation
- API validation
- Mobile automation
- BDD / Gherkin scenarios
- Page Object Model architecture
- Test data management
- Assertions and reusable utilities
- Evidence and reporting
- CI/CD quality gates
- Regression and smoke testing strategy
- Maintainable test code

## 🧩 Capabilities

| Area | Coverage |
|---|---|
| Web Automation | Playwright, selectors, fixtures, POM |
| API Testing | REST, status codes, headers, JSON, schema, response time |
| Mobile Automation | Maestro-oriented mobile test architecture |
| BDD | Gherkin feature/scenario structure |
| Reporting | Allure-compatible reporting architecture |
| CI/CD | GitHub Actions quality gates |
| Engineering | Modular utilities, reusable fixtures, clean test structure |

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
├── Mobile Automation
│   └── Maestro Flows
│
├── BDD
│   └── Gherkin Features
│
├── Reporting
│   └── Allure / Evidence
│
└── CI/CD
    └── GitHub Actions
```

## 🚦 Quality Strategy

SAQA treats automation as an engineering system rather than a collection of scripts.

### Test pyramid

```text
              /\
             /E2E\          Small number
            /----\
           / API  \         Fast feedback
          /--------\
         /   Unit   \       Large coverage
        /------------\
```

Recommended execution order:

1. Static checks
2. Unit/component checks
3. API tests
4. Web smoke tests
5. Regression suite
6. Cross-browser / mobile flows
7. Report + quality gate

## 🌐 Web & API Automation

The framework is intended to support Playwright-based automation with reusable fixtures and Page Object Model design.

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

## 📱 Mobile Automation

Mobile flows can be organized around Maestro-style declarative tests:

```text
mobile/
├── login.yaml
├── checkout.yaml
├── profile.yaml
└── regression/
```

The goal is to keep mobile scenarios readable, deterministic, and easy to execute in CI.

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

BDD is used to communicate behavior and acceptance criteria — not as a replacement for good test design.

## 📊 Reporting & Evidence

A professional execution should answer:

- What was tested?
- What passed?
- What failed?
- Which environment was used?
- What evidence proves the result?
- Which defect or requirement is affected?

The framework is designed for Allure-compatible reporting and CI artifacts.

## ⚙️ CI/CD Quality Gate

A mature pipeline should fail when critical quality conditions are not met.

```text
Push / Pull Request
        ↓
Static Validation
        ↓
API Smoke
        ↓
Web Smoke
        ↓
Regression
        ↓
Report
        ↓
Quality Gate
        ↓
Deploy / Release
```

## 📦 Included Reference Package

The repository currently includes the packaged framework reference:

**`SAQA-Professional-Framework-v1.1.zip`**

Use the documentation in this repository as the architectural guide and the ZIP package as the bundled reference artifact.

## 🗺️ Roadmap

- [x] Professional QA automation architecture
- [x] Web automation direction
- [x] API testing direction
- [x] Mobile automation direction
- [x] BDD / Gherkin guidance
- [x] CI/CD quality-gate strategy
- [x] Reporting strategy
- [ ] Expand executable Playwright examples
- [ ] Add API contract-test examples
- [ ] Add mobile flow examples
- [ ] Add Docker execution profile
- [ ] Add multi-browser CI matrix
- [ ] Add flaky-test detection strategy
- [ ] Add test-data factory examples

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

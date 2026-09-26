# SAQA Professional Framework — Engineering Roadmap

## Status model

- **PASS** — verified by reproducible execution and preserved evidence.
- **FAIL** — verified quality or framework failure.
- **BLOCKED** — execution cannot proceed because a required dependency is unavailable.
- **UNVERIFIED** — evidence is insufficient to make a claim.
- **PENDING** — execution or required evidence is still in progress; certification cannot proceed.
- **N/A** — intentionally not applicable.

A roadmap item is not marked complete merely because code exists; it requires implementation plus appropriate verification evidence.

## Phase 1 — Core Quality Engineering

- [x] Web E2E automation with Playwright
- [x] API validation and response-time gates
- [x] Multi-browser execution
- [x] Database quality gate with isolated SQLite
- [x] Mobile readiness matrix
- [x] Accessibility readiness with independent axe-core oracle
- [x] Performance quality gate
- [x] Dockerized authorized reference targets
- [x] Evidence artifacts and SHA-256 integrity metadata
- [x] Canonical evidence aggregation
- [x] Fail-closed certification semantics

## Phase 2 — CI/CD Quality Control Plane

- [x] GitHub Actions quality-gate orchestration
- [x] Unified PASS / FAIL / BLOCKED / UNVERIFIED classification
- [x] Target authorization policy
- [x] Dependency and secret hygiene
- [x] Trusted Jira automation code from `main`
- [x] Jira synchronization concurrency control
- [x] Stale-main workflow protection
- [x] Pre-bootstrapped Jira control-plane issue policy
- [x] Exact-SHA contract evidence provenance
- [x] Nightly reconciliation using the same contract evidence semantics

## Phase 3 — Observability & Traceability

- [x] Prometheus-compatible SAQA evidence exporter
- [x] Container-safe Prometheus scrape target
- [x] Grafana provisioning structure
- [x] Evidence-to-Jira traceability
- [x] Full Allure-compatible execution/evidence lifecycle
- [x] Historical quality trend storage
- [x] Flaky-test intelligence and quarantine telemetry
- [x] Release-quality dashboard with commit-level certification history

## Phase 4 — Advanced QE

- [x] Advanced API contract/property-based testing
- [x] Expanded negative-path contract fixtures
- [x] Advanced application-security regression on isolated targets
- [x] Resilience and deterministic retry testing
- [x] Broader accessibility oracle coverage
- [x] Cross-service test-data lifecycle management

## Phase 5 — Release Certification

- [x] Automated post-merge main certification
- [x] Multi-domain certification release gate
- [x] Commit-bound tamper-evident evidence bundle
- [x] Immutable release evidence index
- [x] Final certification report generation

## Engineering rule

The project must not claim “complete” or “certified” solely from source inspection. The final release state requires fresh workflow evidence for the exact release commit and no unresolved mandatory FAIL/BLOCKED/UNVERIFIED/PENDING control.

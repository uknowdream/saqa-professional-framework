# Getting Started

This guide takes a new user from clone to the first verified SAQA run.

## 1. Clone

```bash
git clone https://github.com/uknowdream/saqa-professional-framework.git
cd saqa-professional-framework
```

For development work, use the active engineering branch supplied by the project owner rather than assuming `main` contains unreleased features.

## 2. Python environment

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
pip install -e .
```

## 3. Verify the framework

```bash
pytest -q
```

A PASS here validates the framework's local tests only. It does not certify a target application.

## 4. Node/Playwright layer

When the Node test layer is enabled, install dependencies with the committed lockfile:

```bash
npm ci
npx playwright install --with-deps
```

Prefer `npm ci` in CI because it requires a reproducible lockfile. Do not replace a missing lockfile with a hand-written or fabricated one.

## 5. Local security targets

For authoritative security validation, deploy vulnerable benchmarks locally/containerized. Recommended targets are OWASP Juice Shop and OWASP WebGoat.

Keep target ports bound to localhost unless a broader network exposure is explicitly required and authorized.

## 6. Run by capability

Use the documented test commands for the relevant capability. Keep Web, API, DB, accessibility, security, performance, and browser results separate so an infrastructure problem cannot masquerade as an application defect.

## 7. Read the report

Every run should distinguish:

- PASS
- FAIL
- BLOCKED
- UNVERIFIED
- N/A

A missing target, unavailable browser, unavailable Docker daemon, or missing credentials is not a PASS.

## 8. Certification

Certification requires fresh evidence. Evidence must be complete, current, internally consistent, and protected against tampering. A failed or unverifiable mandatory capability prevents a full certification.

## 9. Troubleshooting

If installation fails, first inspect `docs/TROUBLESHOOTING.md`. For CI-only failures, compare the local and runner environments before changing application assertions.

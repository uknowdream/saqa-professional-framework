# SAQA CI Architecture

## Goals

1. **Maintainable** — test intent lives in Python/scripts; workflow YAML is orchestration.
2. **Scalable** — independent quality domains run as separate jobs and browser matrices run concurrently.
3. **Parallelizable** — the Python regression suite uses pytest-xdist; browser/domain matrices use GitHub Actions matrix jobs.
4. **Evidence-first** — every target gate emits deterministic JSON evidence and canonical manifests.

## Execution layers

```text
Pull Request / Push
        |
        +--> Framework Integrity
        +--> Python Quality
        |      +--> pytest-xdist workers
        |      +--> coverage
        |      +--> evidence verification
        +--> Target Authorization
        +--> Juice Shop
        |      +--> E2E browser matrix
        |      +--> API smoke
        |      +--> performance
        +--> WebGoat
        |      +--> E2E browser matrix
        +--> Accessibility
        |      +--> Chromium / Firefox / WebKit
        +--> Mobile Readiness
        |      +--> Chromium / Firefox / WebKit
        +--> Canonical evidence aggregation
        +--> Release certification (main only)
        +--> Jira synchronization / reconciliation
```

## Parallelism policy

- GitHub Actions matrix jobs are independent and use `fail-fast: false` so one browser failure does not hide evidence from other browsers.
- Python tests use `pytest-xdist` with `--dist loadfile` to parallelize modules while keeping tests from the same file together.
- CI uses a 120-second per-test timeout to prevent a hung test from consuming an entire runner indefinitely.
- Pull-request workflows use concurrency groups with cancellation of stale runs. This prevents obsolete commits from consuming runner capacity while preserving the latest commit's evidence.
- Release certification and Jira synchronization use non-canceling concurrency because those decisions are evidence/control-plane operations.

## Target safety

The framework uses explicit local targets:

- Juice Shop: `http://127.0.0.1:3000`
- WebGoat: `http://127.0.0.1:8080`

Browser target gates are read-only and validate origin/redirects before allowing requests. CI target containers are created per job and stopped with `if: always()`.

## Evidence contract

A target gate must:

- emit evidence on success and failure;
- include target, browser/domain, timestamp, status and actionable details;
- distinguish FAIL, BLOCKED, PENDING and UNVERIFIED;
- never infer PASS from missing evidence;
- preserve browser-specific evidence before canonical aggregation.

## Local workflow

```bash
make install
make test
make contract-test
make compile
make target-smoke
```

Focused accessibility regression:

```bash
python -m pytest tests/test_juice_shop_accessibility_gate.py
```

The local commands are limited to the same reproducible/authorized targets used by CI.
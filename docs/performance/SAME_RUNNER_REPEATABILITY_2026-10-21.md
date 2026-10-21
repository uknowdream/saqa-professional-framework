# Same-runner repeatability report — 2026-10-21

## Run provenance

- Workflow: [SAQA Repeated Performance Sample Collection run 39654337570](https://github.com/uknowdream/saqa-professional-framework/actions/runs/39654337570)
- Workflow conclusion: `success`
- Source commit: `c07c259c36fb70662f3c86afe1e0b19e3210426a`
- Artifact: `saqa-performance-samples-c07c259c36fb70662f3c86afe1e0b19e3210426a-39654337570`
- Artifact ID: `12371570393`
- Artifact ZIP size reported by GitHub: 21,842 bytes
- Environment fingerprint: `github-hosted-ubuntu-24.04-x64-k6-1.2.0`
- Exact runner image for both groups: `ubuntu24-20261018.339.1`
- Target: pinned OWASP Juice Shop v20.2.0, loopback only
- Workload: GET products search, workload SHA-256 `f1d082426b3ab0d3ee5869dd1ef101a39b6d9586228324b17a4f9b9daae371d2`
- Policy: `juice-shop-local-performance` version 1, canonical SHA-256 `793b46ba88a2bcbdd797ca186172b3eec7e0b51ba4545f0a0772d704c18b05da`

The artifact contains two groups of five samples (runs 1–5 and runs 6–10), all from the same runner image revision. Every one of the 10 raw-summary files was checked against its run-set SHA-256 entry: **10/10 matched**. The raw summary hashes are preserved in the artifact's `baseline-run-set.json` and `candidate-run-set.json`.

## Median comparison

| Metric | Runs 1–5 | Runs 6–10 | Change | Gate |
|---|---:|---:|---:|---|
| Request median latency | 3.626834 ms | 3.903581 ms | +7.6305% | PASS, within +10% |
| HTTP p95 latency | 6.771894 ms | 7.114063 ms | +5.0528% | PASS, within +10% |
| HTTP p99 latency | 30.193174 ms | 27.793395 ms | −7.9481% | PASS, within +10% |
| Throughput | 24.347030 req/s | 24.305531 req/s | 0.1704% drop | PASS, maximum 10% drop |
| HTTP error rate | 0.0% | 0.0% | No increase | PASS, maximum increase 0.5 percentage points |
| Functional check pass rate | 100% | 100% | No change | PASS, must remain 100% |

The workflow's comparison report returned `status: PASS`, with no failed checks and no warnings for this same-runner pair.

## Interpretation

The second group had a higher median request latency (+7.63%) but stayed within the configured +10% screen. This is **not evidence that the application improved**, nor a proof of stable production capacity; it is an initial repeatability check based on only five runs per group and one hosted runner. The p99 has visible run-to-run dispersion, as expected for tail-latency measurements.

The comparison result explicitly sets `baseline_promotion_eligible: false`. Neither group is automatically promoted as an approved baseline. A maintainer should review archived raw artifacts and collect more runs under controlled conditions before using any baseline for release decisions.

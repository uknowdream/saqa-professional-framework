# Repeated-run performance baseline comparison

The mandatory CI k6 gate continues to enforce versioned absolute guardrails. This separate comparator evaluates **measured** repeated-run sets; it does not create or invent a baseline.

## Input contract

Each JSON file must use schema `saqa.performance-run-set.v1`, contain the same target profile, workload profile, policy ID/version, and environment fingerprint, and include at least five samples. Each sample records `p95_ms`, `p99_ms`, `error_rate`, `throughput_rps`, and `check_pass_rate`. Build run sets from archived, verified k6 artifacts; do not tune sample values to force a pass.

Illustrative shape only (not a shipped baseline):

~~~json
{
  "schema": "saqa.performance-run-set.v1",
  "target_profile": "juice-shop-v20.2.0-local-loopback",
  "workload_profile": "products-search-v1",
  "policy_id": "juice-shop-local-performance",
  "policy_version": 1,
  "environment_fingerprint": "ubuntu-24.04-k6-1.2.0",
  "samples": [
    {"p95_ms": 400, "p99_ms": 700, "error_rate": 0.0, "throughput_rps": 8.0, "check_pass_rate": 1.0}
  ]
}
~~~

The example has one sample to keep the schema readable; real files require five or more.

## Run comparison

~~~bash
python scripts/compare_performance_baseline.py \
  --baseline artifacts/performance/baseline-run-set.json \
  --candidate artifacts/performance/candidate-run-set.json
~~~

Defaults flag p95/p99 median latency increases above 10%, throughput median drops above 10%, error-rate median increase above 0.5 percentage points, or functional check pass rate below 100%. Exit code: 0 pass, 1 regression detected, 2 invalid or incompatible input.

## Interpretation and limits

Medians reduce sensitivity to a single outlier, but this deterministic screen is **not** a statistical significance test. The comparator blocks mismatched target/workload/policy/environment metadata and insufficient samples. Keep runner, target version, workload, and test configuration controlled; review distributions and uncertainty before treating small changes as meaningful. Do not interpret local reference-target results as production SLO certification.

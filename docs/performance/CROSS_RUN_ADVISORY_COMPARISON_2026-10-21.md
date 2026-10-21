# Advisory cross-run performance comparison — 2026-10-21

## Provenance

This is a **measured, exploratory comparison**, not an approved performance baseline and not production SLO evidence. It was prepared from raw artifacts of two successful runs of the SAQA repeated-sample workflow:

| Role | Workflow run | Source commit | Artifact ID | Runner image fingerprint |
|---|---|---|---:|---|
| Baseline sample set | [39650358628](https://github.com/uknowdream/saqa-professional-framework/actions/runs/39650358628) | `3e0f54620c96944fc707d3020df8242c21e143a2` | `12370685389` | `ubuntu24-20261018.339.1` |
| Candidate sample set | [39650409504](https://github.com/uknowdream/saqa-professional-framework/actions/runs/39650409504) | `d5bc42536655747898592b634102f409b3c81fa9` | `12368633764` | `ubuntu24-20261012.334.1` |

Both run sets use the pinned Juice Shop v20.2.0 loopback target, the `products-search-v1` GET workload, policy `juice-shop-local-performance` version 1, workload SHA-256 `f1d082426b3ab0d3ee5869dd1ef101a39b6d9586228324b17a4f9b9daae371d2`, and canonical policy SHA-256 `793b46ba88a2bcbdd797ca186172b3eec7e0b51ba4545f0a0772d704c18b05da`.

The five raw-summary SHA-256 references in each run set were checked against the summary bytes preserved inside their workflow artifacts; no mismatches were found.

## Comparison of medians

| Metric | Baseline (5 samples) | Candidate (5 samples) | Change | Configured limit |
|---|---:|---:|---:|---:|
| Request median latency | 5.637121 ms | 4.319726 ms | -23.3700% | no more than +10% |
| HTTP p95 latency | 8.534926 ms | 7.030342 ms | -17.6286% | no more than +10% |
| HTTP p99 latency | 33.984673 ms | 24.158389 ms | -28.9139% | no more than +10% |
| Throughput | 24.021555 req/s | 24.236388 req/s | +0.8943% | drop no more than 10% |
| HTTP error rate | 0.0% | 0.0% | 0.0 percentage points | increase no more than 0.5 percentage points |
| Functional check pass rate | 100% | 100% | unchanged | 100% |

Under the configured median-based thresholds, **no regression was observed** in this comparison.

## Mandatory caveat

The runner image revisions differ. The comparator now normalizes those two legacy fingerprints to the same compatibility profile, preserves both exact revisions in its output, and emits an explicit warning. The apparent latency improvement must therefore be treated as **advisory**: runner image/build changes can affect measurements, and this comparison is not a statistical-significance test.

`baseline_promotion_eligible` remains `false`. Do not promote either run set to an approved baseline automatically. A maintainer must review the raw artifacts, runner difference, workload/policy identity, repeatability, and any desired release use. These feature-branch sample runs are not used as trusted `main` release-certification evidence.

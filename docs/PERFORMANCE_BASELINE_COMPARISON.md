# Building a measured performance run set

The builder converts raw k6 summary files into a run set for the repeated-run comparator. It requires at least five separate summaries and records the SHA-256 of each input file.

~~~bash
python scripts/build_performance_run_set.py \
  --summary artifacts/performance/run-1/k6-summary.json \
  --summary artifacts/performance/run-2/k6-summary.json \
  --summary artifacts/performance/run-3/k6-summary.json \
  --summary artifacts/performance/run-4/k6-summary.json \
  --summary artifacts/performance/run-5/k6-summary.json \
  --policy performance/baselines/juice-shop-local-v1.json \
  --target-profile juice-shop-v20.2.0-local-loopback \
  --workload-profile products-search-v1 \
  --environment-fingerprint ubuntu-24.04-k6-1.2.0 \
  --output artifacts/performance/run-set.json
~~~

The target, workload, and environment labels are supplied by the operator and are not independently discovered. Keep them accurate and consistent between baseline and candidate. Preserve original run artifacts and trusted provenance separately: hashes identify bytes but do not prove who generated them. Do not combine runs from different target versions, workload profiles, policy versions, or materially different runners.

Then compare the run sets using scripts/compare_performance_baseline.py. A passing result means only that configured median-based checks stayed within limits; it is not statistical significance or a production SLO.
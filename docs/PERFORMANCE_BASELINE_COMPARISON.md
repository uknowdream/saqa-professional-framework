# Building a measured performance run set

The builder converts raw k6 summary files into a run set for the repeated-run comparator. It requires at least five separate summaries and records the SHA-256 of each input file and a canonical SHA-256 of the exact versioned policy.

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

The target, workload, and environment labels are supplied by the operator and are not independently discovered. Keep them accurate and consistent between baseline and candidate. Preserve original run artifacts and trusted provenance separately: hashes identify bytes but do not prove who generated them. Do not combine runs from different target versions, workload profiles, policy versions or policy contents, or materially different runners.

Then compare the run sets using scripts/compare_performance_baseline.py. A passing result means only that configured median-based checks stayed within limits; it is not statistical significance or a production SLO.

## Collecting a measured candidate run set

The manual/scheduled workflow `.github/workflows/saqa-performance-samples.yml` runs the pinned local target five separate times, retains each raw k6 summary and gate evidence, and builds a run-set candidate whose source paths are relative to the raw-artifact directory. It uploads the candidate and raw evidence for 30 days. Any individual run that fails the absolute guardrails causes the workflow to fail after evidence upload.

A collected run set is **not automatically promoted to an approved baseline**. Review the run, runner image, workload, policy version, raw source digests, and test results first. Download the artifact, keep its raw files together, and pass the raw-artifact directories as `--baseline-source-root` and `--candidate-source-root` to the comparator. The comparison workflow also verifies that both selected run IDs belong to completed, successful runs of the measured-sample workflow in this repository. Compare against a separate approved baseline collected under the same metadata. The scheduled and manual triggers become available only after this workflow file is present on the repository default branch. For a trusted baseline candidate, run the collector from `main`; the comparison workflow deliberately rejects sample runs from feature branches or forks.

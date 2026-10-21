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
  --environment-fingerprint github-hosted-ubuntu-24.04-x64-k6-1.2.0 \
  --workload-script performance/k6/juice-shop.js \
  --output artifacts/performance/run-set.json
~~~

The target, workload, and environment labels are supplied by the operator and are not independently discovered. Keep them accurate and consistent between baseline and candidate. Preserve original run artifacts and trusted provenance separately: hashes identify bytes but do not prove who generated them. Do not combine runs from different target versions, workload profiles, policy versions or policy contents, operating-system families, architectures, or load-generation runtimes. GitHub-hosted image build revisions within the same supported Ubuntu 24.04 x64 + pinned-k6 profile are retained separately and surfaced as a comparison warning rather than silently discarded.

Then compare the run sets using scripts/compare_performance_baseline.py. A passing result means only that configured median-based checks stayed within limits; it is not statistical significance or a production SLO.

## Collecting a measured candidate run set

The manual/scheduled workflow `.github/workflows/saqa-performance-samples.yml` runs the pinned local target ten separate times using fresh application containers, retains each raw k6 summary and gate evidence, and builds two independent five-sample run sets on the same runner. It then compares those sets using the same target, workload-script hash, policy digest, and runner fingerprint. Absolute guardrail failures or a blocked/failed repeatability comparison make the workflow fail after evidence upload. The raw samples, both run sets, and comparison report are retained for 30 days.

A collected run set is **not automatically promoted to an approved baseline**. Review the run, runner image, workload, policy version, raw source digests, and test results first. Download the artifact, keep its raw files together, and pass the raw-artifact directories as `--baseline-source-root` and `--candidate-source-root` to the comparator. The comparison workflow also verifies that both selected run IDs belong to completed, successful runs of the measured-sample workflow in this repository. Compare against a separate approved baseline collected under the same metadata. The scheduled and manual triggers become available only after this workflow file is present on the repository default branch. For a trusted baseline candidate, run the collector from `main`; the comparison workflow deliberately rejects sample runs from feature branches or forks.

The run-set builder hashes the exact k6 workload script into `workload_sha256`; the comparator verifies this digest against the supplied script in addition to checking raw summary hashes and the canonical policy SHA-256. This prevents comparing samples that merely share a human-entered workload label while their k6 script differs. The exact runner image revision remains in the output; differences add a warning and set `baseline_promotion_eligible: false`. This allows measured trend comparison without silently treating different image builds as identical, and no approved baseline is ever promoted automatically.


## Preserved same-runner repeatability evidence

The latest ten-sample run produced a same-runner 5-vs-5 repeatability comparison. The raw sample hashes matched the contents of the uploaded artifact. The measured medians remained within the configured thresholds, but median request latency increased by 7.63% from the first group to the second; this is a repeatability screen, not a claim of improvement. See [the dated report](performance/SAME_RUNNER_REPEATABILITY_2026-10-21.md) and [workflow run 39654337570](https://github.com/uknowdream/saqa-professional-framework/actions/runs/39654337570). No baseline is promoted automatically.

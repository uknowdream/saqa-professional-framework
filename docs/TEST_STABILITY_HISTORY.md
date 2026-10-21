# Cross-run test stability history

SAQA creates an advisory trend report from retained `junit.xml` artifacts for recent completed **main-branch** CI runs. The workflow downloads up to 12 eligible `push` / `schedule` runs and keeps Python 3.11, 3.12, and 3.13 in separate cohorts to avoid conflating interpreter-specific failures.

## What the report distinguishes

- **`SAME_COMMIT_OUTCOME_VARIATION`** — the same test has PASS and FAIL/ERROR observations for the same commit SHA in distinct workflow runs. This is a candidate intermittent result that merits investigation.
- **`CROSS_COMMIT_OUTCOME_VARIATION`** — outcomes differ, but observations span different SHAs. This could be a code regression, test change, dependency change, or environment variation; it is not called flakiness.
- **`NO_VARIATION_OBSERVED`** — sufficient observed history has no outcome variation. This does not prove the test will remain stable.
- **`INCOMPLETE_ARTIFACT_COVERAGE`** — one or more expected Python-version JUnit artifacts are missing from the selected history, including cases where no JUnit files remain.
- **`INSUFFICIENT_HISTORY`** — fewer than three downloaded CI runs are available for one or more Python cohorts, without a more specific outcome or artifact-coverage signal.

The workflow is scheduled weekly and can be run manually. It uploads the report together with the retained input JUnit files for 90 days. Test artifacts also use 90-day retention so recent history can be reconstructed when available. Missing historical artifacts are reported as gaps; the collector never fabricates outcomes.

## Important limits

This is cross-run outcome telemetry, not retry-aware flake-rate measurement. Each observation is the final result recorded in JUnit. To estimate retry rate or determine whether a failure was recovered by a retry, the framework needs retry-aware runner events or explicit per-attempt records. A report status is informational and does not change CI, certification, or a failing test into PASS.

After the workflow has run on `main`, inspect the artifact `saqa-test-stability-history-<run-id>`. The scheduled workflow begins collecting once the workflow definition is present on the repository default branch.

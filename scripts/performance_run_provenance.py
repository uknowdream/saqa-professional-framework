"""Validate provenance of GitHub Actions performance sample artifacts."""
from __future__ import annotations
import re
from typing import Any

EXPECTED_WORKFLOW_NAME = "SAQA Repeated Performance Sample Collection"
EXPECTED_WORKFLOW_PATH = ".github/workflows/saqa-performance-samples.yml"
ALLOWED_EVENTS = {"workflow_dispatch", "schedule"}
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def validate_sample_run(
    run: Any,
    *,
    expected_repo: str,
    requested_run_id: str,
    artifact_name: str,
) -> dict[str, str]:
    """Accept only completed main-branch sample runs and their exact run-bound artifact."""
    if not isinstance(run, dict):
        raise ValueError("sample workflow run must be a JSON object")
    if not isinstance(expected_repo, str) or not expected_repo.strip() or "/" not in expected_repo:
        raise ValueError("expected_repo must be an owner/repository name")
    if not isinstance(requested_run_id, str) or not requested_run_id.isdigit() or int(requested_run_id) <= 0:
        raise ValueError("requested run ID must be a positive integer")
    run_id = run.get("id")
    if isinstance(run_id, bool) or not isinstance(run_id, int) or run_id <= 0 or str(run_id) != requested_run_id:
        raise ValueError("GitHub run ID does not match the requested run ID")
    if run.get("status") != "completed" or run.get("conclusion") != "success":
        raise ValueError("sample run must be completed successfully")
    if run.get("name") != EXPECTED_WORKFLOW_NAME or run.get("path") != EXPECTED_WORKFLOW_PATH:
        raise ValueError("run did not originate from the expected performance sample workflow")
    repository = run.get("head_repository")
    if not isinstance(repository, dict) or repository.get("full_name") != expected_repo:
        raise ValueError("sample run originated from a different repository")
    if run.get("head_branch") != "main":
        raise ValueError("performance samples must originate from the reviewed main branch")
    if run.get("event") not in ALLOWED_EVENTS:
        raise ValueError("sample run must use workflow_dispatch or schedule")
    head_sha = run.get("head_sha")
    if not isinstance(head_sha, str) or not SHA_RE.fullmatch(head_sha):
        raise ValueError("sample run head_sha must be a full lowercase commit SHA")
    expected_artifact = f"saqa-performance-samples-{head_sha}-{run_id}"
    if not isinstance(artifact_name, str) or artifact_name != expected_artifact:
        raise ValueError("artifact name must match the selected run's exact commit SHA and run ID")
    return {
        "run_id": str(run_id),
        "head_sha": head_sha,
        "head_branch": "main",
        "event": str(run["event"]),
        "workflow_path": EXPECTED_WORKFLOW_PATH,
        "artifact_name": expected_artifact,
    }

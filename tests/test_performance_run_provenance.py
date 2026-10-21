import copy
from pathlib import Path

import pytest

from scripts.performance_run_provenance import validate_sample_run

REPO = "uknowdream/saqa-professional-framework"
SHA = "a" * 40
RUN_ID = 123456
ARTIFACT = f"saqa-performance-samples-{SHA}-{RUN_ID}"


def run():
    return {
        "id": RUN_ID,
        "name": "SAQA Repeated Performance Sample Collection",
        "path": ".github/workflows/saqa-performance-samples.yml",
        "status": "completed",
        "conclusion": "success",
        "head_branch": "main",
        "head_sha": SHA,
        "event": "workflow_dispatch",
        "head_repository": {"full_name": REPO},
    }


def validate(record=None, **overrides):
    args = {
        "expected_repo": REPO,
        "requested_run_id": str(RUN_ID),
        "artifact_name": ARTIFACT,
    }
    args.update(overrides)
    return validate_sample_run(run() if record is None else record, **args)


def test_valid_main_branch_sample_run_passes():
    result = validate()
    assert result["run_id"] == str(RUN_ID)
    assert result["head_sha"] == SHA
    assert result["artifact_name"] == ARTIFACT


@pytest.mark.parametrize(("field", "value", "message"), [
    ("head_branch", "feature/unreviewed", "main branch"),
    ("status", "in_progress", "completed successfully"),
    ("conclusion", "failure", "completed successfully"),
    ("path", ".github/workflows/other.yml", "expected performance sample workflow"),
    ("name", "Other workflow", "expected performance sample workflow"),
    ("head_sha", "not-a-full-sha", "full lowercase commit SHA"),
    ("event", "pull_request", "workflow_dispatch or schedule"),
])
def test_untrusted_sample_run_is_rejected(field, value, message):
    record = run()
    record[field] = value
    with pytest.raises(ValueError, match=message):
        validate(record)


def test_cross_repository_run_is_rejected():
    record = run()
    record["head_repository"]["full_name"] = "someone-else/fork"
    with pytest.raises(ValueError, match="different repository"):
        validate(record)


def test_run_id_mismatch_is_rejected():
    record = run()
    record["id"] += 1
    with pytest.raises(ValueError, match="does not match"):
        validate(record)


def test_artifact_must_be_bound_to_exact_run_and_commit():
    with pytest.raises(ValueError, match="exact commit SHA and run ID"):
        validate(artifact_name="saqa-performance-samples-" + SHA + "-999")


@pytest.mark.parametrize("bad_id", ["", "abc", "0", "-1"])
def test_invalid_requested_run_id_is_rejected(bad_id):
    with pytest.raises(ValueError, match="positive integer"):
        validate(requested_run_id=bad_id)


def test_unexpected_root_payload_is_rejected():
    with pytest.raises(ValueError, match="JSON object"):
        validate([])



def test_compare_workflow_enforces_provenance_helper_and_exact_artifact_names():
    workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "saqa-performance-compare.yml").read_text(encoding="utf-8")
    assert "from scripts.performance_run_provenance import validate_sample_run" in workflow
    assert "BASELINE_ARTIFACT_NAME: ${{ inputs.baseline_artifact_name }}" in workflow
    assert "CANDIDATE_ARTIFACT_NAME: ${{ inputs.candidate_artifact_name }}" in workflow
    assert "expected_repo=repo" in workflow
    assert "artifact_name=os.environ[artifact_key]" in workflow


def test_different_head_sha_is_rejected():
    record = run()
    record["head_sha"] = "b" * 40
    with pytest.raises(ValueError, match="exact commit SHA and run ID"):
        validate(record)


def test_schedule_event_is_allowed_for_measured_sample_run():
    record = run()
    record["event"] = "schedule"
    assert validate(record)["event"] == "schedule"

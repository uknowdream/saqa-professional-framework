from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from scripts.qa_release_gate import (
    ALLOWED_RELEASE_EVENTS,
    MANDATORY,
    MANDATORY_WORKFLOW_IDENTITIES,
    decide,
    latest_by_workflow,
    normalize_runs,
    result,
    select_runs,
)

NOW = datetime(2026, 10, 12, 7, 30, tzinfo=timezone.utc)
SHA = "b" * 40


def make_run(name: str = MANDATORY[0], **overrides):
    path, workflow_id = MANDATORY_WORKFLOW_IDENTITIES[name]
    started = (NOW - timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
    value = {
        "id": 123,
        "run_attempt": 1,
        "name": name,
        "path": path,
        "workflow_id": int(workflow_id),
        "status": "completed",
        "conclusion": "success",
        "head_sha": SHA,
        "head_branch": "main",
        "event": "push",
        "created_at": started,
        "run_started_at": started,
        "updated_at": started,
        "html_url": "https://github.com/example/repo/actions/runs/123",
    }
    value.update(overrides)
    return value


def test_release_certification_requires_five_unique_mandatory_domains():
    assert len(MANDATORY) == 5
    assert len(MANDATORY) == len(set(MANDATORY))
    assert set(MANDATORY_WORKFLOW_IDENTITIES) == set(MANDATORY)
    assert len({value[0] for value in MANDATORY_WORKFLOW_IDENTITIES.values()}) == 5
    assert len({value[1] for value in MANDATORY_WORKFLOW_IDENTITIES.values()}) == 5


def test_select_runs_requires_exact_sha_main_branch_and_release_event():
    raw = {"workflow_runs": [
        make_run(id=1, head_sha="a" * 40),
        make_run(id=2, event="pull_request"),
        make_run(id=3, head_branch="feature"),
        make_run(id=4, event="push"),
        make_run(id=5, event="workflow_dispatch"),
        make_run(id=6, event="schedule"),
    ]}
    assert [r["run_id"] for r in select_runs(raw, SHA, "push")] == ["4"]
    assert [r["run_id"] for r in select_runs(raw, SHA)] == ["4", "5"]
    with pytest.raises(ValueError, match="release event must be push or workflow_dispatch"):
        select_runs(raw, SHA, "pull_request")


def test_normalizer_preserves_exact_workflow_identity_and_malformed_ids():
    normalized = normalize_runs({"workflow_runs": [make_run(id=None)]})[0]
    assert normalized["path"] == MANDATORY_WORKFLOW_IDENTITIES[MANDATORY[0]][0]
    assert normalized["workflow_id"] == MANDATORY_WORKFLOW_IDENTITIES[MANDATORY[0]][1]
    assert normalized["run_id"] == ""
    with pytest.raises(ValueError, match="invalid workflow run ID"):
        latest_by_workflow([normalized])


@pytest.mark.parametrize("field,value,expected", [
    ("path", ".github/workflows/other.yml", "workflow path mismatch"),
    ("workflow_id", 999999999, "workflow ID mismatch"),
])
def test_latest_run_must_match_exact_workflow_identity(field, value, expected):
    record = make_run(**{field: value})
    with pytest.raises(ValueError, match=expected):
        latest_by_workflow(normalize_runs([record]))


def test_latest_attempt_wins_even_when_it_fails():
    first = make_run(id=500, run_attempt=1, conclusion="success")
    retry = make_run(id=500, run_attempt=2, conclusion="failure")
    selected = latest_by_workflow(normalize_runs([first, retry]))
    assert selected[MANDATORY[0]]["run_attempt"] == "2"
    assert result(selected[MANDATORY[0]], now=NOW) == "FAIL"


def test_stale_success_is_not_pass():
    started = (NOW - timedelta(hours=7)).isoformat().replace("+00:00", "Z")
    assert result(normalize_runs([make_run(run_started_at=started)])[0], now=NOW) == "STALE"


def test_fresh_success_requires_positive_attempt_and_timestamp():
    assert result(normalize_runs([make_run()])[0], now=NOW) == "PASS"
    assert result(normalize_runs([make_run(run_attempt=0)])[0], now=NOW) == "UNVERIFIED"
    assert result(normalize_runs([make_run(run_started_at="not-a-time")])[0], now=NOW) == "UNVERIFIED"


def test_certification_never_passes_missing_or_stale_domains():
    assert decide({name: "PASS" for name in MANDATORY}).status == "CERTIFIED"
    assert decide({name: "UNVERIFIED" for name in MANDATORY}).status == "NOT_CERTIFIED"
    statuses = {name: "PASS" for name in MANDATORY}
    statuses[MANDATORY[0]] = "STALE"
    assert decide(statuses).status == "NOT_CERTIFIED"


def test_duplicate_identity_with_conflicting_conclusion_fails_closed():
    first = normalize_runs([make_run(id=900, run_attempt=2)])[0]
    conflict = dict(first, conclusion="failure")
    with pytest.raises(ValueError, match="conflicting duplicate workflow run identity"):
        latest_by_workflow([first, conflict])


def test_release_event_allowlist_is_exact():
    assert ALLOWED_RELEASE_EVENTS == {"push", "workflow_dispatch"}

from scripts.qa_release_gate import MANDATORY, decide, normalize_runs, result, select_runs


def test_release_certification_requires_all_quality_domains():
    assert MANDATORY == (
        "SAQA CI",
        "SAQA Contract Testing",
        "SAQA Accessibility",
        "SAQA Mobile Readiness",
        "SAQA k6 Performance",
    )
    assert len(MANDATORY) == len(set(MANDATORY))

def test_release_gate_requires_exact_sha_and_optional_event():
    sha = "b" * 40
    raw = {"workflow_runs": [
        {"id": 1, "name": MANDATORY[0], "status": "completed", "conclusion": "success", "head_sha": "a" * 40, "head_branch": "main", "event": "push"},
        {"id": 2, "name": MANDATORY[0], "status": "completed", "conclusion": "success", "head_sha": sha, "head_branch": "main", "event": "pull_request"},
        {"id": 3, "name": MANDATORY[0], "status": "completed", "conclusion": "success", "head_sha": sha, "head_branch": "feature", "event": "push"},
        {"id": 4, "name": MANDATORY[0], "status": "completed", "conclusion": "success", "head_sha": sha, "head_branch": "main", "event": "push"},
    ]}
    assert [r["run_id"] for r in select_runs(raw, sha, "push")] == ["4"]
    assert [r["run_id"] for r in select_runs(raw, "a" * 40, "push")] == ["1"]
    assert select_runs(raw, sha, "pull_request") == []

def test_release_gate_never_certifies_missing_domains():
    assert decide({name: "PASS" for name in MANDATORY}).status == "CERTIFIED"
    incomplete = {name: "PASS" for name in MANDATORY[:-1]}
    assert decide(incomplete).status == "NOT_CERTIFIED"

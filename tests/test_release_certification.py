from __future__ import annotations

from scripts.qa_release_gate import decide, result


def test_result_is_fail_closed() -> None:
    assert result(None) == "UNVERIFIED"
    assert result({"status": "queued", "conclusion": ""}) == "PENDING"
    assert result({"status": "completed", "conclusion": "success"}) == "PASS"
    assert result({"status": "completed", "conclusion": "failure"}) == "FAIL"
    assert result({"status": "completed", "conclusion": "cancelled"}) == "BLOCKED"


def test_certification_requires_every_mandatory_domain() -> None:
    passing = {
        "SAQA CI": "PASS",
        "SAQA Contract Testing": "PASS",
        "SAQA Accessibility": "PASS",
        "SAQA Mobile Readiness": "PASS",
        "SAQA k6 Performance": "PASS",
    }
    assert decide(passing).status == "CERTIFIED"
    failed = {**passing, "SAQA Accessibility": "FAIL"}
    assert decide(failed).status == "NOT_CERTIFIED"
    pending = {**passing, "SAQA Contract Testing": "PENDING"}
    assert decide(pending).status == "NOT_CERTIFIED"
    unverified = {**passing, "SAQA Contract Testing": "UNVERIFIED"}
    assert decide(unverified).status == "NOT_CERTIFIED"

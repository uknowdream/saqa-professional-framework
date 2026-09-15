from __future__ import annotations

from scripts.qa_release_gate import decide, result


def test_result_is_fail_closed() -> None:
    assert result(None) == "UNVERIFIED"
    assert result({"status": "queued", "conclusion": ""}) == "PENDING"
    assert result({"status": "completed", "conclusion": "success"}) == "PASS"
    assert result({"status": "completed", "conclusion": "failure"}) == "FAIL"
    assert result({"status": "completed", "conclusion": "cancelled"}) == "BLOCKED"


def test_certification_requires_every_mandatory_domain() -> None:
    assert decide({"SAQA CI": "PASS", "SAQA Accessibility": "PASS", "SAQA Mobile Readiness": "PASS"}).status == "CERTIFIED"
    assert decide({"SAQA CI": "PASS", "SAQA Accessibility": "FAIL", "SAQA Mobile Readiness": "PASS"}).status == "NOT_CERTIFIED"
    assert decide({"SAQA CI": "PASS", "SAQA Accessibility": "PENDING", "SAQA Mobile Readiness": "PASS"}).status == "NOT_CERTIFIED"
    assert decide({"SAQA CI": "PASS", "SAQA Accessibility": "UNVERIFIED", "SAQA Mobile Readiness": "PASS"}).status == "NOT_CERTIFIED"

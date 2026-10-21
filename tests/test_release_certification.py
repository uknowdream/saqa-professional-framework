from __future__ import annotations

from datetime import datetime, timezone

from scripts.qa_release_gate import decide, result


def test_result_is_fail_closed() -> None:
    assert result(None) == "UNVERIFIED"
    assert result({"status": "queued", "conclusion": ""}) == "PENDING"
    stamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    assert result({"status": "completed", "conclusion": "success", "run_attempt": "1", "run_started_at": stamp}) == "PASS"
    assert result({"status": "completed", "conclusion": "success"}) == "UNVERIFIED"
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



def test_release_workflow_fails_when_readiness_is_not_certified():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/qa-release-certification.yml").read_text(encoding="utf-8")
    upload = workflow.index("Upload readiness decision")
    fail_closed = workflow.index("Fail closed when the release is not ready")
    assert upload < fail_closed
    assert "if: steps.check.outputs.ready != 'true'" in workflow
    assert "Release not certified" in workflow
    assert "exit 1" in workflow[fail_closed:workflow.index("certify:", fail_closed)]

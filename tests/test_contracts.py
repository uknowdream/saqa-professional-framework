import pytest

from saqa.contracts import Evidence, ResultStatus, is_certification_safe, validate_evidence


def test_evidence_factory_creates_valid_execution_record():
    item = Evidence.now("WEB-001", "web", ResultStatus.PASS, duration_ms=12.5)
    validate_evidence(item)
    assert item.status is ResultStatus.PASS
    assert item.duration_ms == 12.5


@pytest.mark.parametrize("status", [ResultStatus.FAIL, ResultStatus.BLOCKED, ResultStatus.UNVERIFIED])
def test_non_pass_states_are_not_certification_safe(status):
    assert not is_certification_safe(status)


def test_na_is_explicitly_certification_safe():
    assert is_certification_safe(ResultStatus.NA)


def test_negative_duration_is_rejected():
    item = Evidence.now("API-001", "api", ResultStatus.PASS, duration_ms=-1)
    with pytest.raises(ValueError, match="negative"):
        validate_evidence(item)

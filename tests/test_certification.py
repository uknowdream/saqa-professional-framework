from saqa.certification import certify
from saqa.contracts import ResultStatus


def test_certification_rejects_missing_capability():
    result = certify([("web-1", "web", ResultStatus.PASS)], ["web", "api"])
    assert not result.certified
    assert result.missing_capabilities == ("api",)


def test_certification_rejects_blocking_result():
    result = certify(
        [("web-1", "web", ResultStatus.PASS), ("api-1", "api", ResultStatus.FAIL)],
        ["web", "api"],
    )
    assert not result.certified
    assert result.blocking_test_ids == ("api-1",)


def test_certification_accepts_explicit_passes():
    result = certify(
        [("web-1", "web", ResultStatus.PASS), ("api-1", "api", ResultStatus.PASS)],
        ["web", "api"],
    )
    assert result.certified


def test_certification_does_not_hide_unverified():
    result = certify(
        [("web-1", "web", ResultStatus.PASS), ("api-1", "api", ResultStatus.UNVERIFIED)],
        ["web", "api"],
    )
    assert not result.certified
    assert result.blocking_test_ids == ("api-1",)

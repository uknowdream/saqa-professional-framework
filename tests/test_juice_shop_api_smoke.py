import pytest

from scripts.juice_shop_api_smoke import OUTPUT, _assert_loopback_http


def test_api_target_is_strict_loopback_http_only() -> None:
    _assert_loopback_http("http://127.0.0.1:3000")
    for target in ("http://localhost:3000", "https://127.0.0.1:3000", "http://127.0.0.1", "http://example.test:3000"):
        with pytest.raises(ValueError):
            _assert_loopback_http(target)


def test_api_evidence_output_contract_is_deterministic() -> None:
    output = OUTPUT
    assert output.name == "juice-shop-api.json"
    assert output.parent.as_posix() == "artifacts/targets"

from pathlib import Path

import pytest

from scripts.juice_shop_api_smoke import _assert_loopback_http


def test_api_target_is_loopback_http_only() -> None:
    _assert_loopback_http("http://127.0.0.1:3000")
    _assert_loopback_http("http://localhost:3000")

    with pytest.raises(ValueError):
        _assert_loopback_http("https://127.0.0.1:3000")
    with pytest.raises(ValueError):
        _assert_loopback_http("http://example.test:3000")


def test_api_evidence_output_contract_is_deterministic() -> None:
    output = Path("artifacts/targets/juice-shop-api.json")
    assert output.name == "juice-shop-api.json"
    assert output.parent.as_posix() == "artifacts/targets"

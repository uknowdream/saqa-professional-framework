from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "juice_shop_mobile_readiness.py"


def load_module():
    spec = importlib.util.spec_from_file_location("juice_shop_mobile_readiness", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_loopback_http_is_accepted():
    module = load_module()
    module._assert_loopback_http("http://127.0.0.1:3000")
    module._assert_loopback_http("http://localhost:3000")


def test_non_loopback_targets_are_rejected():
    module = load_module()
    for target in ("https://127.0.0.1:3000", "http://example.com", "http://192.168.1.10:3000"):
        try:
            module._assert_loopback_http(target)
        except ValueError:
            pass
        else:
            raise AssertionError(f"target should be rejected: {target}")

from pathlib import Path
import importlib.util

SCRIPT = Path(__file__).parents[1] / "scripts" / "juice_shop_accessibility_gate.py"
spec = importlib.util.spec_from_file_location("juice_shop_accessibility_gate", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_accessibility_target_rejects_non_loopback():
    try:
        module._assert_loopback_http("https://example.com")
    except ValueError:
        return
    raise AssertionError("non-loopback target was accepted")


def test_accessibility_target_rejects_remote_http():
    try:
        module._assert_loopback_http("http://example.com")
    except ValueError:
        return
    raise AssertionError("remote target was accepted")


def test_accessibility_target_accepts_loopback_http():
    module._assert_loopback_http("http://127.0.0.1:3000")
    module._assert_loopback_http("http://localhost:3000")


def test_browser_allowlist_is_explicit():
    assert module.ALLOWED_BROWSERS == {"chromium", "firefox", "webkit"}

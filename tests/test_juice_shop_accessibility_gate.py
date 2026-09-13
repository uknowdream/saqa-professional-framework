from pathlib import Path
import importlib.util

SCRIPT = Path(__file__).parents[1] / "scripts" / "juice_shop_accessibility_gate.py"
spec = importlib.util.spec_from_file_location("juice_shop_accessibility_gate", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
SOURCE = SCRIPT.read_text(encoding="utf-8")


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


def test_accessible_name_resolution_handles_real_label_sources():
    assert "aria-labelledby" in SOURCE
    assert "document.getElementById(id)" in SOURCE
    assert "label[for=" in SOURCE
    assert "closest('label')" in SOURCE
    assert "getAttribute('title')" in SOURCE


def test_accessibility_gate_records_actionable_control_details():
    assert "unnamed_control_details" in SOURCE
    assert "outerHTML.slice(0, 300)" in SOURCE
    assert "tab_index" in SOURCE


def test_independent_accessibility_oracle_is_required():
    assert module.AXE_RULES == ["aria-input-field-name", "button-name", "link-name", "label"]
    assert "axe-core" in SOURCE
    assert "CONFIRMED_ORACLE" in SOURCE
    assert "INCONCLUSIVE" in SOURCE


def test_heuristic_classification_is_fail_closed_for_uncorroborated_controls():
    assert module._classify_heuristic_finding([], 0) == "NONE"
    assert module._classify_heuristic_finding([{"tab_index": -1}], 0) == "INCONCLUSIVE"
    assert module._classify_heuristic_finding([{"tab_index": 0}], 0) == "INCONCLUSIVE"
    assert module._classify_heuristic_finding([{"tab_index": -1}], 1) == "CONFIRMED_ORACLE"


def test_accessibility_oracle_path_is_explicitly_configurable():
    assert "SAQA_AXE_CORE_PATH" in SOURCE
    assert "node_modules/axe-core/axe.min.js" in SOURCE

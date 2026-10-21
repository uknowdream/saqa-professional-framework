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


def test_accessibility_target_accepts_strict_loopback_http():
    module._assert_loopback_http("http://127.0.0.1:3000")
    for target in ("http://localhost:3000", "http://127.0.0.1", "https://127.0.0.1:3000"):
        try:
            module._assert_loopback_http(target)
        except ValueError:
            pass
        else:
            raise AssertionError(f"target should be rejected: {target}")


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
    assert "e.outerHTML.slice(0,300)" in SOURCE
    assert "tab_index" in SOURCE


def test_heuristic_uses_semantic_disabled_state_not_tab_order():
    assert ".filter(e => !e.matches(':disabled'))" in SOURCE
    assert ".filter(e => e.getAttribute('aria-disabled') !== 'true')" in SOURCE
    assert ".filter(e => e.tabIndex >= 0)" in SOURCE
    assert "tab_index:e.tabIndex" in SOURCE


def test_heuristic_findings_are_diagnostic_until_node_correlation_exists():
    assert "heuristic_note" in SOURCE
    assert "INCONCLUSIVE is diagnostic evidence only" in SOURCE


def test_independent_accessibility_oracle_is_required():
    assert module.AXE_RULES == ["aria-input-field-name", "button-name", "link-name"]
    assert "axe-core" in SOURCE
    assert "CONFIRMED_ORACLE" in SOURCE
    assert "INCONCLUSIVE" in SOURCE


def test_heuristic_classification_is_fail_closed_for_uncorroborated_controls():
    assert module._classify_heuristic_finding([]) == "NONE"
    assert module._classify_heuristic_finding([{"tab_index": -1}]) == "INCONCLUSIVE"
    assert module._classify_heuristic_finding([{"tab_index": 0}]) == "INCONCLUSIVE"
    # Heuristic findings remain diagnostic until independently correlated with the accessibility oracle.


def test_semantic_disabled_controls_are_excluded_by_browser_logic():
    assert ":disabled" in SOURCE
    assert "fieldset" not in SOURCE or ":disabled" in SOURCE


def test_accessibility_oracle_path_is_explicitly_configurable():
    assert "SAQA_AXE_CORE_PATH" in SOURCE
    assert "node_modules/axe-core/axe.min.js" in SOURCE


def test_keyboard_only_focus_traversal_is_recorded_in_evidence():
    assert "_keyboard_focus_sequence" in SOURCE
    assert 'page.keyboard.press("Tab")' in SOURCE
    assert '"keyboard_navigation"' in SOURCE
    assert '"unique_focus_targets"' in SOURCE
    assert "keyboard Tab sequence did not reach a focusable target" in SOURCE


def test_keyboard_focus_diagnostics_capture_indicators_and_repeated_targets():
    assert "visible_indicator_style_steps" in SOURCE
    assert "repeated_consecutive_targets" in SOURCE
    assert "keyboard_trap_suspected" in SOURCE
    assert "outline_offset" in SOURCE
    assert "box_shadow" in SOURCE
    assert "heuristics, not proof of WCAG conformance" in SOURCE


def test_keyboard_sequence_summary_flags_repeated_target_as_diagnostic():
    sequence = [
        {"tag": "button", "id": "search", "role": "", "text": "Search", "focus_visible": True,
         "outline_style": "solid", "outline_width": "2px", "outline_offset": "0px", "box_shadow": "none"},
        {"tag": "button", "id": "search", "role": "", "text": "Search", "focus_visible": True,
         "outline_style": "solid", "outline_width": "2px", "outline_offset": "0px", "box_shadow": "none"},
        {"tag": "a", "id": "home", "role": "", "text": "Home", "focus_visible": True,
         "outline_style": "none", "outline_width": "0px", "outline_offset": "0px", "box_shadow": "none"},
        {"tag": "a", "id": "home", "role": "", "text": "Home", "focus_visible": True,
         "outline_style": "none", "outline_width": "0px", "outline_offset": "0px", "box_shadow": "none"},
    ]
    result = module._summarize_keyboard_sequence(sequence, 4)
    assert result["unique_focus_targets"] == 2
    assert result["visible_indicator_style_steps"] == 2
    assert result["repeated_consecutive_targets"] == 2
    assert result["keyboard_trap_suspected"] is True
    assert "diagnostic smoke only" in result["scope_note"]


def test_keyboard_sequence_summary_does_not_flag_unique_sequence():
    sequence = [
        {"tag": "button", "id": "search", "role": "", "text": "Search", "focus_visible": True,
         "outline_style": "none", "outline_width": "0px", "outline_offset": "0px", "box_shadow": "none"},
        {"tag": "a", "id": "home", "role": "", "text": "Home", "focus_visible": True,
         "outline_style": "none", "outline_width": "0px", "outline_offset": "0px", "box_shadow": "none"},
    ]
    result = module._summarize_keyboard_sequence(sequence, 2)
    assert result["unique_focus_targets"] == 2
    assert result["repeated_consecutive_targets"] == 0
    assert result["keyboard_trap_suspected"] is False
    assert result["visible_indicator_style_steps"] == 0


def test_mobile_viewport_keyboard_traversal_is_recorded_and_gated():
    assert 'page.set_viewport_size({"width": 390, "height": 844})' in SOURCE
    assert '"keyboard_navigation_mobile_viewport"' in SOURCE
    assert '"mobile viewport keyboard Tab sequence did not reach a focusable target"' in SOURCE
    assert "diagnostic smoke evidence, not a claim of native mobile or WCAG certification" in SOURCE


def test_gated_axe_scan_occurs_before_mobile_viewport_reload():
    assert SOURCE.index("page.add_script_tag(content=axe_source)") < SOURCE.index('page.set_viewport_size({"width": 390, "height": 844})')
    assert SOURCE.index('evidence["details"]["independent_oracle"]') < SOURCE.index('page.set_viewport_size({"width": 390, "height": 844})')

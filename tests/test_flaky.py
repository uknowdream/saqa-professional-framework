from saqa.flaky import analyze_history

def test_flaky_transition_is_explicit():
    result=analyze_history(["PASS","FAIL","PASS"])
    assert result.status=="FLAKY"
    assert result.transition_count==2

def test_stable_results_are_not_flaky():
    assert analyze_history(["PASS","PASS"]).status=="STABLE_PASS"
    assert analyze_history(["FAIL","FAIL"]).status=="STABLE_FAIL"

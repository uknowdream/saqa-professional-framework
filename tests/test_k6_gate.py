import pytest
from scripts.k6_gate import evaluate_summary

POLICY = {"schema":"saqa.performance-guardrails.v1","policy_id":"juice-shop-local-performance","version":1,"target_profile":"juice-shop-v20.2.0-local-loopback","limits":{"p95_max_ms":1000,"p99_max_ms":1500,"error_rate_max":0.01,"throughput_min_rps":1.0,"check_pass_rate_min":1.0}}

def summary(*, p95=400, p99=700, error_rate=0, throughput=8, check_rate=1):
    return {"metrics":{"http_req_duration":{"values":{"p(95)":p95,"p(99)":p99}},"http_req_failed":{"values":{"rate":error_rate}},"http_reqs":{"values":{"rate":throughput}},"checks":{"values":{"value":check_rate}}}}

def test_performance_summary_passes_and_is_versioned():
    result=evaluate_summary(summary(),POLICY)
    assert result["status"]=="PASS" and result["policy_version"]==1
    assert result["metrics"]["p95_ms"]==400 and result["metrics"]["p99_ms"]==700
    assert result["metrics"]["throughput_rps"]==8

@pytest.mark.parametrize(("measurement","expected"),[
    ({"p95":1001},"p95_latency"),({"p99":1501},"p99_latency"),({"error_rate":0.02},"http_error_rate"),
    ({"throughput":0.5},"throughput"),({"check_rate":0.99},"check_pass_rate")])
def test_each_guardrail_fails_closed(measurement,expected):
    result=evaluate_summary(summary(**measurement),POLICY)
    assert result["status"]=="FAIL" and expected in result["failed_checks"]

def test_missing_metric_fails_closed():
    with pytest.raises(ValueError,match="missing numeric metric"):
        evaluate_summary({"metrics":{}},POLICY)

def test_unsupported_policy_schema_is_rejected():
    with pytest.raises(ValueError,match="unsupported"):
        evaluate_summary(summary(),{**POLICY,"schema":"unknown"})

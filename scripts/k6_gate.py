"""Run a local k6 gate and compare measured percentiles to a versioned guardrail."""
from __future__ import annotations
import hashlib, json, os, subprocess, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path(os.getenv("SAQA_K6_OUTPUT", "artifacts/targets/juice-shop-k6.json"))
SCRIPT = Path(os.getenv("SAQA_K6_SCRIPT", "performance/k6/juice-shop.js"))
POLICY = Path(os.getenv("SAQA_K6_POLICY", "performance/baselines/juice-shop-local-v1.json"))
CONTAINER = f"saqa-k6-gate-{os.getpid()}-{time.time_ns()}"

def evaluate_summary(summary: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    """Return normalized measurements and fail-closed guardrail results."""
    if policy.get("schema") != "saqa.performance-guardrails.v1":
        raise ValueError("unsupported performance policy schema")
    required = {"p95_max_ms", "p99_max_ms", "error_rate_max", "throughput_min_rps", "check_pass_rate_min"}
    limits = policy.get("limits")
    if not isinstance(limits, dict) or not required.issubset(limits):
        raise ValueError("performance policy is missing required limits")
    metrics = summary.get("metrics")
    if not isinstance(metrics, dict):
        raise ValueError("k6 summary is missing metrics")
    def metric(name: str, key: str) -> float:
        record = metrics.get(name)
        values = record.get("values") if isinstance(record, dict) else None
        value = values.get(key) if isinstance(values, dict) else None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"k6 summary missing numeric metric {name}.{key}")
        return float(value)
    observed = {
        "p95_ms": metric("http_req_duration", "p(95)"),
        "p99_ms": metric("http_req_duration", "p(99)"),
        "error_rate": metric("http_req_failed", "rate"),
        "throughput_rps": metric("http_reqs", "rate"),
        "check_pass_rate": metric("checks", "value"),
    }
    checks = [
        {"id":"p95_latency","observed":observed["p95_ms"],"operator":"<=","limit":limits["p95_max_ms"],"passed":observed["p95_ms"] <= limits["p95_max_ms"]},
        {"id":"p99_latency","observed":observed["p99_ms"],"operator":"<=","limit":limits["p99_max_ms"],"passed":observed["p99_ms"] <= limits["p99_max_ms"]},
        {"id":"http_error_rate","observed":observed["error_rate"],"operator":"<=","limit":limits["error_rate_max"],"passed":observed["error_rate"] <= limits["error_rate_max"]},
        {"id":"throughput","observed":observed["throughput_rps"],"operator":">=","limit":limits["throughput_min_rps"],"passed":observed["throughput_rps"] >= limits["throughput_min_rps"]},
        {"id":"check_pass_rate","observed":observed["check_pass_rate"],"operator":">=","limit":limits["check_pass_rate_min"],"passed":observed["check_pass_rate"] >= limits["check_pass_rate_min"]},
    ]
    failed = [item["id"] for item in checks if not item["passed"]]
    return {"status":"FAIL" if failed else "PASS","policy_id":policy.get("policy_id"),"policy_version":policy.get("version"),"target_profile":policy.get("target_profile"),"metrics":observed,"checks":checks,"failed_checks":failed}

def main() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    summary_path = OUTPUT.with_name("k6-summary.json")
    summary_path.unlink(missing_ok=True)
    started = time.perf_counter()
    evidence = {"schema":"saqa.k6-gate.v3","test_id":"juice-shop.performance.k6-products-search","status":"BLOCKED","target":"http://127.0.0.1:3000","http_methods":["GET"],"destructive_actions":False,"observed_at":datetime.now(timezone.utc).isoformat(),"details":{"script":str(SCRIPT),"policy":str(POLICY),"summary_file":str(summary_path)}}
    if not SCRIPT.is_file() or not POLICY.is_file():
        evidence["status"] = "FAIL"
        evidence["details"]["error"] = f"required file missing: script={SCRIPT.is_file()} policy={POLICY.is_file()}"
    else:
        try:
            completed = subprocess.run(["docker","run","--rm","--name",CONTAINER,"--user",f"{os.getuid()}:{os.getgid()}","--network","host","-v",f"{SCRIPT.parent.resolve()}:/scripts:ro","-v",f"{OUTPUT.parent.resolve()}:/artifacts:rw","grafana/k6:1.2.0","run","--summary-export=/artifacts/k6-summary.json",f"/scripts/{SCRIPT.name}"],capture_output=True,text=True,timeout=120,check=False)
            evidence["details"].update({"exit_code":completed.returncode,"elapsed_ms":round((time.perf_counter()-started)*1000,2),"stdout_tail":completed.stdout[-4000:],"stderr_tail":completed.stderr[-4000:]})
            if summary_path.is_file():
                try:
                    summary = json.loads(summary_path.read_text(encoding="utf-8"))
                    policy = json.loads(POLICY.read_text(encoding="utf-8"))
                    evaluated = evaluate_summary(summary, policy)
                    evidence["details"]["performance_regression"] = evaluated
                    evidence["details"]["raw_summary_sha256"] = hashlib.sha256(summary_path.read_bytes()).hexdigest()
                    evidence["status"] = "PASS" if completed.returncode == 0 and evaluated["status"] == "PASS" else "FAIL"
                except (OSError, json.JSONDecodeError, ValueError) as exc:
                    evidence["status"] = "FAIL"
                    evidence["details"]["summary_evaluation_error"] = f"{type(exc).__name__}: {exc}"
            else:
                evidence["status"] = "FAIL"
                evidence["details"]["error"] = "k6 did not produce the required summary export"
        except subprocess.TimeoutExpired as exc:
            evidence["status"] = "BLOCKED"
            evidence["details"].update({"error":f"TimeoutExpired: {exc}","elapsed_ms":round((time.perf_counter()-started)*1000,2)})
        except OSError as exc:
            evidence["status"] = "BLOCKED"
            evidence["details"]["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            try:
                subprocess.run(["docker","rm","-f",CONTAINER],capture_output=True,text=True,timeout=15,check=False)
            except (OSError, subprocess.TimeoutExpired) as exc:
                evidence["details"]["cleanup_error"] = f"{type(exc).__name__}: {exc}"
    OUTPUT.write_text(json.dumps(evidence,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(evidence,indent=2,sort_keys=True))
    return 0 if evidence["status"] == "PASS" else 1

if __name__ == "__main__":
    raise SystemExit(main())

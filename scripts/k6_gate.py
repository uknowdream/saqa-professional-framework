"""Run a local k6 gate and compare measured percentiles to a versioned guardrail."""
from __future__ import annotations
import hashlib, json, math, os, re, shutil, subprocess, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
def repo_path(env_name: str, default: str) -> Path:
    """Resolve configured paths consistently, independent of the caller's cwd."""
    value = Path(os.getenv(env_name, default)).expanduser()
    return value if value.is_absolute() else ROOT / value

OUTPUT = repo_path("SAQA_K6_OUTPUT", "artifacts/targets/juice-shop-k6.json")
SCRIPT = repo_path("SAQA_K6_SCRIPT", "performance/k6/juice-shop.js")
POLICY = repo_path("SAQA_K6_POLICY", "performance/baselines/juice-shop-local-v1.json")
CONTAINER = f"saqa-k6-gate-{os.getpid()}-{time.time_ns()}"

def evaluate_summary(summary: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    """Return normalized measurements and fail-closed guardrail results."""
    if policy.get("schema") != "saqa.performance-guardrails.v1":
        raise ValueError("unsupported performance policy schema")
    if not isinstance(policy.get("policy_id"), str) or not policy["policy_id"].strip():
        raise ValueError("performance policy requires a non-empty policy_id")
    if isinstance(policy.get("version"), bool) or not isinstance(policy.get("version"), int) or policy["version"] < 1:
        raise ValueError("performance policy version must be a positive integer")
    if not isinstance(policy.get("target_profile"), str) or not policy["target_profile"].strip():
        raise ValueError("performance policy requires a non-empty target_profile")
    metric_names = policy.get("metrics")
    required_metric_keys = {"latency", "error_rate", "throughput", "functional_checks"}
    if not isinstance(metric_names, dict) or not required_metric_keys.issubset(metric_names):
        raise ValueError("performance policy is missing required metric mappings")
    if any(not isinstance(metric_names[key], str) or not metric_names[key].strip() for key in required_metric_keys):
        raise ValueError("performance policy metric mappings must be non-empty strings")
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
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"k6 summary metric {name}.{key} must be finite")
        return number
    observed = {
        "p95_ms": metric(metric_names["latency"], "p(95)"),
        "p99_ms": metric(metric_names["latency"], "p(99)"),
        "error_rate": metric(metric_names["error_rate"], "rate"),
        "throughput_rps": metric(metric_names["throughput"], "rate"),
        "check_pass_rate": metric(metric_names["functional_checks"], "rate"),
    }
    for key in required:
        value = limits[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError(f"performance policy limit {key} must be a finite number")
    for key in ("p95_max_ms", "p99_max_ms", "throughput_min_rps"):
        if limits[key] < 0:
            raise ValueError(f"performance policy limit {key} must be non-negative")
    for key in ("error_rate_max", "check_pass_rate_min"):
        if not 0 <= limits[key] <= 1:
            raise ValueError(f"performance policy limit {key} must be between 0 and 1")
    if limits["p95_max_ms"] > limits["p99_max_ms"]:
        raise ValueError("performance policy p95_max_ms must not exceed p99_max_ms")
    for key in ("p95_ms", "p99_ms", "throughput_rps"):
        if observed[key] < 0:
            raise ValueError(f"k6 summary metric {key} must be non-negative")
    if observed["p95_ms"] > observed["p99_ms"]:
        raise ValueError("k6 summary p95_ms must not exceed p99_ms")
    for key in ("error_rate", "check_pass_rate"):
        if not 0 <= observed[key] <= 1:
            raise ValueError(f"k6 summary metric {key} must be between 0 and 1")
    checks = [
        {"id":"p95_latency","observed":observed["p95_ms"],"operator":"<=","limit":limits["p95_max_ms"],"passed":observed["p95_ms"] <= limits["p95_max_ms"]},
        {"id":"p99_latency","observed":observed["p99_ms"],"operator":"<=","limit":limits["p99_max_ms"],"passed":observed["p99_ms"] <= limits["p99_max_ms"]},
        {"id":"http_error_rate","observed":observed["error_rate"],"operator":"<=","limit":limits["error_rate_max"],"passed":observed["error_rate"] <= limits["error_rate_max"]},
        {"id":"throughput","observed":observed["throughput_rps"],"operator":">=","limit":limits["throughput_min_rps"],"passed":observed["throughput_rps"] >= limits["throughput_min_rps"]},
        {"id":"check_pass_rate","observed":observed["check_pass_rate"],"operator":">=","limit":limits["check_pass_rate_min"],"passed":observed["check_pass_rate"] >= limits["check_pass_rate_min"]},
    ]
    failed = [item["id"] for item in checks if not item["passed"]]
    return {"status":"FAIL" if failed else "PASS","policy_id":policy.get("policy_id"),"policy_version":policy.get("version"),"target_profile":policy.get("target_profile"),"metrics":observed,"checks":checks,"failed_checks":failed}

def validate_script_thresholds(script_text: str, policy: dict[str, Any]) -> None:
    """Prevent the k6 runtime thresholds from drifting from the versioned policy."""
    checks = {
        "http_req_failed": (r'http_req_failed:\s*\["rate<=([0-9.eE+-]+)"\]', policy["limits"]["error_rate_max"]),
        "p95": (r'"p\(95\)<=([0-9.eE+-]+)"', policy["limits"]["p95_max_ms"]),
        "p99": (r'"p\(99\)<=([0-9.eE+-]+)"', policy["limits"]["p99_max_ms"]),
        "checks": (r'checks:\s*\["rate>=([0-9.eE+-]+)"\]', policy["limits"]["check_pass_rate_min"]),
    }
    for name, (pattern, expected) in checks.items():
        match = re.search(pattern, script_text)
        if not match or not math.isclose(float(match.group(1)), float(expected), rel_tol=0.0, abs_tol=1e-12):
            raise ValueError(f"k6 script threshold {name} does not match the versioned policy")

def main() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    summary_path = OUTPUT.with_name("k6-summary.json")
    summary_path.unlink(missing_ok=True)
    scratch = OUTPUT.parent / f".k6-scratch-{os.getpid()}-{time.time_ns()}"
    scratch.mkdir(parents=True, exist_ok=False)
    scratch_summary = scratch / "k6-summary.json"
    started = time.perf_counter()
    evidence = {"schema":"saqa.k6-gate.v3","test_id":"juice-shop.performance.k6-products-search","status":"BLOCKED","target":"http://127.0.0.1:3000","http_methods":["GET"],"destructive_actions":False,"observed_at":datetime.now(timezone.utc).isoformat(),"details":{"script":str(SCRIPT),"policy":str(POLICY),"summary_file":str(summary_path)}}
    if not SCRIPT.is_file() or not POLICY.is_file():
        evidence["status"] = "FAIL"
        evidence["details"]["error"] = f"required file missing: script={SCRIPT.is_file()} policy={POLICY.is_file()}"
    else:
        try:
            policy = json.loads(POLICY.read_text(encoding="utf-8"))
            validate_script_thresholds(SCRIPT.read_text(encoding="utf-8"), policy)
            command = ["docker", "run", "--rm", "--name", CONTAINER]
            # --user is needed on POSIX to keep exported artifacts writable;
            # os.getuid/getgid are not available on Windows.
            if hasattr(os, "getuid") and hasattr(os, "getgid"):
                command.extend(["--user", f"{os.getuid()}:{os.getgid()}"])
            command.extend([
                "--network", "host",
                "-v", f"{SCRIPT.parent.resolve()}:/scripts:ro",
                "-v", f"{scratch.resolve()}:/artifacts:rw",
                "grafana/k6:1.2.0", "run", f"/scripts/{SCRIPT.name}",
            ])
            completed = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
            if scratch_summary.is_file():
                shutil.copy2(scratch_summary, summary_path)
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
        except (json.JSONDecodeError, ValueError) as exc:
            evidence["status"] = "FAIL"
            evidence["details"]["configuration_error"] = f"{type(exc).__name__}: {exc}"
        except subprocess.TimeoutExpired as exc:
            evidence["status"] = "BLOCKED"
            stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            evidence["details"].update({"error":f"TimeoutExpired: {exc}","elapsed_ms":round((time.perf_counter()-started)*1000,2),"stdout_tail":stdout[-4000:],"stderr_tail":stderr[-4000:]})
        except OSError as exc:
            evidence["status"] = "BLOCKED"
            evidence["details"]["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            try:
                subprocess.run(["docker","rm","-f",CONTAINER],capture_output=True,text=True,timeout=15,check=False)
            except (OSError, subprocess.TimeoutExpired) as exc:
                evidence["details"]["cleanup_error"] = f"{type(exc).__name__}: {exc}"
    shutil.rmtree(scratch, ignore_errors=True)
    OUTPUT.write_text(json.dumps(evidence,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(evidence,indent=2,sort_keys=True))
    return 0 if evidence["status"] == "PASS" else 1

if __name__ == "__main__":
    raise SystemExit(main())

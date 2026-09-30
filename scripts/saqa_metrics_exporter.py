"""Expose SAQA evidence and commit certification as Prometheus metrics."""
from __future__ import annotations
import json, os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
HOST=os.getenv("SAQA_METRICS_HOST","127.0.0.1")
PORT=int(os.getenv("SAQA_METRICS_PORT","9109"))
EVIDENCE_DIR=Path(os.getenv("SAQA_EVIDENCE_DIR","artifacts/targets"))
RELEASE_REPORT=Path(os.getenv("SAQA_RELEASE_REPORT","artifacts/release-certification.json"))
FLAKY_REPORT=Path(os.getenv("SAQA_FLAKY_REPORT","artifacts/observability/flaky-telemetry.json"))
STATUS_VALUE={"PASS":1,"FAIL":0,"BLOCKED":-1,"PENDING":-2,"UNVERIFIED":-3}
def _escape_label(value: object)->str:
    return str(value).replace("\\","\\\\").replace("\n","\\n").replace('"','\\"')
def collect()->str:
    lines=["# HELP saqa_quality_status Current normalized quality status.","# TYPE saqa_quality_status gauge","# HELP saqa_quality_evidence_total Number of evidence records discovered.","# TYPE saqa_quality_evidence_total gauge","# HELP saqa_release_certified Whether the current commit is release-certified.","# TYPE saqa_release_certified gauge","# HELP saqa_release_report_info Whether a release certification report is available.","# TYPE saqa_release_report_info gauge","# HELP saqa_flaky_test_total Number of tests classified as flaky.","# TYPE saqa_flaky_test_total gauge","# HELP saqa_flaky_report_info Whether flaky telemetry is available.","# TYPE saqa_flaky_report_info gauge"]
    count=0
    for path in sorted(EVIDENCE_DIR.glob("*.json")):
        try: data=json.loads(path.read_text(encoding="utf-8"))
        except (OSError,json.JSONDecodeError): continue
        if not isinstance(data,dict): continue
        status=str(data.get("status","UNVERIFIED")).upper()
        lines.append(f'saqa_quality_status{{test_id="{_escape_label(data.get("test_id",path.stem))}",status="{_escape_label(status)}"}} {STATUS_VALUE.get(status,-3)}')
        count+=1
    lines.append(f"saqa_quality_evidence_total {count}")
    release_available=0; certified=0; commit=""
    if RELEASE_REPORT.exists():
        try:
            report=json.loads(RELEASE_REPORT.read_text(encoding="utf-8"))
            if isinstance(report,dict):
                release_available=1
                certified=1 if report.get("certified") is True or report.get("status") == "CERTIFIED" else 0
                commit=str(report.get("commit_sha") or report.get("head_sha") or "")
        except (OSError,json.JSONDecodeError): pass
    lines.append(f'saqa_release_report_info{{reported="{str(bool(release_available)).lower()}"}} 1')
    lines.append(f'saqa_release_certified{{commit_sha="{_escape_label(commit)}"}} {certified}')
    flaky_available=0; flaky_total=0
    if FLAKY_REPORT.exists():
        try:
            telemetry=json.loads(FLAKY_REPORT.read_text(encoding="utf-8"))
            if isinstance(telemetry,dict):
                flaky_available=1
                tests=telemetry.get("tests",{})
                if isinstance(tests,dict): flaky_total=sum(1 for item in tests.values() if isinstance(item,dict) and item.get("status")=="FLAKY")
        except (OSError,json.JSONDecodeError): pass
    lines.append(f'saqa_flaky_report_info{{reported="{str(bool(flaky_available)).lower()}"}} 1')
    lines.append(f"saqa_flaky_test_total {flaky_total}")
    return "\n".join(lines)+"\n"
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path!="/metrics": self.send_response(404); self.end_headers(); return
        body=collect().encode(); self.send_response(200); self.send_header("Content-Type","text/plain; version=0.0.4"); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self,format,*args): return
if __name__=="__main__": ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()

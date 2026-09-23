"""Expose SAQA evidence as Prometheus metrics for local observability."""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = "0.0.0.0"
PORT = int(os.getenv("SAQA_METRICS_PORT", "9109"))
EVIDENCE_DIR = Path(os.getenv("SAQA_EVIDENCE_DIR", "artifacts/targets"))
STATUS_VALUE = {"PASS": 1, "FAIL": 0, "BLOCKED": -1, "PENDING": -2, "UNVERIFIED": -3}


def collect() -> str:
    lines = [
        "# HELP saqa_quality_status Current normalized quality status.",
        "# TYPE saqa_quality_status gauge",
        "# HELP saqa_quality_evidence_total Number of evidence records discovered.",
        "# TYPE saqa_quality_evidence_total gauge",
    ]
    count = 0
    for path in sorted(EVIDENCE_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        status = str(data.get("status", "UNVERIFIED")).upper()
        test_id = str(data.get("test_id", path.stem)).replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'saqa_quality_status{{test_id="{test_id}",status="{status}"}} {STATUS_VALUE.get(status, -3)}')
        count += 1
    lines.append(f"saqa_quality_evidence_total {count}")
    return "\n".join(lines) + "\n"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != "/metrics":
            self.send_response(404)
            self.end_headers()
            return
        body = collect().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        return


if __name__ == "__main__":
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()

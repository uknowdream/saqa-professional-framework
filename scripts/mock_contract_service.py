"""Minimal local HTTP contract fixture for deterministic contract-gate tests."""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HOST = "127.0.0.1"
PORT = int(os.getenv("SAQA_MOCK_PORT", "3100"))
MODE = os.getenv("SAQA_MOCK_MODE", "valid")


class Handler(BaseHTTPRequestHandler):
    server_version = "SAQA-Mock/1.0"

    def _send(self, status: int, payload, content_type: str = "application/json") -> None:
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send(200, {"status": "ok"})
            return
        if parsed.path != "/rest/products/search":
            self._send(404, {"error": "not found"})
            return

        query = parse_qs(parsed.query).get("q", [""])[0]
        if not query:
            self._send(400, {"error": "q is required"})
            return

        if MODE == "http-500":
            self._send(500, {"error": "simulated server failure"})
        elif MODE == "malformed-json":
            self._send(200, b"not-json")
        elif MODE == "wrong-content-type":
            self._send(200, {"data": [{"id": 1, "name": "Apple"}]}, "text/plain")
        elif MODE == "invalid-schema":
            self._send(200, {"data": [{"id": "1", "name": "Apple"}]})
        elif MODE == "missing-data":
            self._send(200, {"query": query})
        else:
            self._send(200, {"data": [{"id": 1, "name": "Apple"}]})

    def log_message(self, format: str, *args) -> None:
        return


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"SAQA mock contract service listening on http://{HOST}:{PORT} mode={MODE}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()

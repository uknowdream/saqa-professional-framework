#!/usr/bin/env bash
set -Eeuo pipefail

COMPOSE_FILE="${SAQA_COMPOSE_FILE:-docker-compose.qa-targets.yml}"
ARTIFACT_DIR="${SAQA_ARTIFACT_DIR:-artifacts/targets}"
mkdir -p "$ARTIFACT_DIR"

cleanup() {
  docker compose -f "$COMPOSE_FILE" down --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required" >&2
  exit 2
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "docker compose plugin is required" >&2
  exit 2
fi

docker compose -f "$COMPOSE_FILE" config >/dev/null

docker compose -f "$COMPOSE_FILE" pull --quiet
docker compose -f "$COMPOSE_FILE" up -d

wait_http() {
  local name="$1" url="$2" max_attempts="${3:-60}"
  local attempt=1
  local delay=2
  local status=""

  # Containerized targets can briefly reset/close connections while the
  # application server is starting. Treat those as transient readiness
  # failures and keep the bounded retry loop quiet and deterministic.
  while (( attempt <= max_attempts )); do
    status="$(curl --silent --output /dev/null --write-out '%{http_code}' --max-time 5 "$url" 2>/dev/null || true)"
    if [[ "$status" =~ ^2[0-9][0-9]$ ]]; then
      printf '%s:PASS (attempt %d/%d, HTTP %s)\n' "$name" "$attempt" "$max_attempts" "$status"
      return 0
    fi

    if (( attempt < max_attempts )); then
      sleep "$delay"
    fi
    ((attempt++))
  done

  printf '%s:FAIL (after %d attempts, last HTTP result: %s)\n' "$name" "$max_attempts" "${status:-no-response}" >&2
  echo "--- $name container diagnostics ---" >&2
  docker compose -f "$COMPOSE_FILE" ps >&2 || true
  docker compose -f "$COMPOSE_FILE" logs --tail=80 >&2 || true
  return 1
}

# Read-only, loopback-only validation. No mutating HTTP methods are issued.
wait_http "juice-shop-web" "http://127.0.0.1:3000/" 60
wait_http "juice-shop-api" "http://127.0.0.1:3000/rest/products/search?q=apple" 60
wait_http "webgoat-web" "http://127.0.0.1:8080/WebGoat/" 90

python scripts/api_contract_smoke.py
python scripts/juice_shop_e2e.py

python - <<'PY'
import json, os, platform, subprocess, time
from pathlib import Path

out = Path(os.environ.get("SAQA_ARTIFACT_DIR", "artifacts/targets"))
out.mkdir(parents=True, exist_ok=True)
compose = os.environ.get("SAQA_COMPOSE_FILE", "docker-compose.qa-targets.yml")
result = {
    "schema": "saqa.target-smoke.v1",
    "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "compose_file": compose,
    "targets": ["owasp-juice-shop", "owasp-webgoat"],
    "http_methods": ["GET"],
    "destructive_actions": False,
    "runner": platform.platform(),
}
try:
    result["compose_ps"] = subprocess.check_output(
        ["docker", "compose", "-f", compose, "ps", "--format", "json"],
        text=True,
        stderr=subprocess.STDOUT,
    )
except subprocess.CalledProcessError as exc:
    result["compose_ps_error"] = exc.output
    raise
path = out / "target-smoke.json"
path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
sha256sum "$ARTIFACT_DIR/target-smoke.json" > "$ARTIFACT_DIR/target-smoke.sha256"
cat "$ARTIFACT_DIR/target-smoke.json"
cat "$ARTIFACT_DIR/target-smoke.sha256"

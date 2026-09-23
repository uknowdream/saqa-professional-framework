#!/usr/bin/env bash
set -Eeuo pipefail

COMPOSE_FILE="${SAQA_COMPOSE_FILE:-docker-compose.qa-targets.yml}"
ARTIFACT_DIR="${SAQA_ARTIFACT_DIR:-artifacts/targets}"
mkdir -p "$ARTIFACT_DIR"
completed=0

cleanup() {
  local rc=$?
  docker compose -f "$COMPOSE_FILE" down --remove-orphans >/dev/null 2>&1 || true
  if (( completed == 0 )); then
    python - "$ARTIFACT_DIR/target-smoke.json" "$rc" "$COMPOSE_FILE" <<'PY'
import json, platform, sys, time
from pathlib import Path
path, rc, compose = sys.argv[1], int(sys.argv[2]), sys.argv[3]
payload = {"schema":"saqa.target-smoke.v4","timestamp_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"compose_file":compose,"targets":["owasp-juice-shop","owasp-webgoat"],"http_methods":["GET"],"redirects_followed":False,"destructive_actions":False,"runner":platform.platform(),"status":"FAIL","exit_code":rc,"details":"target smoke failed before completion; inspect CI diagnostics"}
Path(path).write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n",encoding="utf-8")
PY
  fi
  return "$rc"
}
trap cleanup EXIT

if ! command -v docker >/dev/null 2>&1; then echo "docker is required" >&2; exit 2; fi
if ! docker compose version >/dev/null 2>&1; then echo "docker compose plugin is required" >&2; exit 2; fi

docker compose -f "$COMPOSE_FILE" config >/dev/null
docker compose -f "$COMPOSE_FILE" pull --quiet
docker compose -f "$COMPOSE_FILE" up -d

wait_http() {
  local name="$1" url="$2" max_attempts="${3:-60}" allow_local_redirect="${4:-false}" attempt=1 delay=2 status="" location="" header_file=""
  while (( attempt <= max_attempts )); do
    header_file="$(mktemp)"
    status="$(curl --silent --show-error --output /dev/null --dump-header "$header_file" --write-out '%{http_code}' --max-time 5 --max-redirs 0 "$url" 2>/dev/null || true)"
    if [[ "$status" =~ ^2[0-9][0-9]$ ]]; then
      rm -f "$header_file"
      printf '%s:PASS (attempt %d/%d, HTTP %s)\n' "$name" "$attempt" "$max_attempts" "$status"
      return 0
    fi
    if [[ "$status" =~ ^3[0-9][0-9]$ && "$allow_local_redirect" == "true" ]]; then
      location="$(awk 'tolower($0) ~ /^location:/{sub(/\r$/,"",$0); sub(/^[^:]*:[[:space:]]*/,"",$0); print; exit}' "$header_file")"
      rm -f "$header_file"
      if [[ "$location" =~ ^http://127\.0\.0\.1:8080/WebGoat(/|$) ]] || [[ "$location" =~ ^/WebGoat(/|$) ]]; then
        printf '%s:PASS (attempt %d/%d, HTTP %s, validated local redirect)\n' "$name" "$attempt" "$max_attempts" "$status"
        return 0
      fi
      printf '%s:FAIL (unsafe redirect location: %s)\n' "$name" "${location:-missing}" >&2
      return 1
    fi
    rm -f "$header_file"
    if [[ "$status" =~ ^3[0-9][0-9]$ ]]; then
      printf '%s:FAIL (unexpected redirect response HTTP %s; redirects are not followed)\n' "$name" "$status" >&2
      return 1
    fi
    if (( attempt < max_attempts )); then sleep "$delay"; fi
    ((attempt++))
  done
  printf '%s:FAIL (after %d attempts, last HTTP result: %s)\n' "$name" "$max_attempts" "${status:-no-response}" >&2
  docker compose -f "$COMPOSE_FILE" ps >&2 || true
  docker compose -f "$COMPOSE_FILE" logs --tail=80 >&2 || true
  return 1
}

wait_http "juice-shop-web" "http://127.0.0.1:3000/" 60
wait_http "juice-shop-api" "http://127.0.0.1:3000/rest/products/search?q=apple" 60
wait_http "webgoat-web" "http://127.0.0.1:8080/WebGoat/" 90 true
python scripts/api_contract_smoke.py
python scripts/juice_shop_e2e.py

python - <<'PY'
import json, os, platform, subprocess, time
from pathlib import Path
out=Path(os.environ.get("SAQA_ARTIFACT_DIR","artifacts/targets")); out.mkdir(parents=True,exist_ok=True)
compose=os.environ.get("SAQA_COMPOSE_FILE","docker-compose.qa-targets.yml")
result={"schema":"saqa.target-smoke.v4","timestamp_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"compose_file":compose,"targets":["owasp-juice-shop","owasp-webgoat"],"http_methods":["GET"],"redirects_followed":False,"destructive_actions":False,"runner":platform.platform(),"status":"PASS"}
result["compose_ps"]=subprocess.check_output(["docker","compose","-f",compose,"ps","--format","json"],text=True,stderr=subprocess.STDOUT)
path=out/"target-smoke.json"; path.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
PY
sha256sum "$ARTIFACT_DIR/target-smoke.json" > "$ARTIFACT_DIR/target-smoke.sha256"
cat "$ARTIFACT_DIR/target-smoke.json"
cat "$ARTIFACT_DIR/target-smoke.sha256"
completed=1

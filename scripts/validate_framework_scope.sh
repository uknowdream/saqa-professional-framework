#!/usr/bin/env bash
set -euo pipefail

fail() { echo "FRAMEWORK_SCOPE_FAIL: $1" >&2; exit 1; }

required=(
  README.md
  CONTRIBUTING.md
  LICENSE
  docs/GETTING_STARTED.md
  docker-compose.qa-targets.yml
  src/saqa/__init__.py
  src/saqa/api.py
  src/saqa/browser_smoke.py
  src/saqa/certification.py
  src/saqa/ci_evidence.py
  src/saqa/contracts.py
  src/saqa/evidence.py
  src/saqa/target_registry.py
)

for path in "${required[@]}"; do
  test -f "$path" || fail "missing required path: $path"
done

grep -q '127\.0\.0\.1:3000:3000' docker-compose.qa-targets.yml || fail 'Juice Shop is not loopback-bound'
grep -q '127\.0\.0\.1:8080:8080' docker-compose.qa-targets.yml || fail 'WebGoat is not loopback-bound'
grep -q 'bkimminich/juice-shop:v20\.2\.0' docker-compose.qa-targets.yml || fail 'Juice Shop image/version is not pinned'
grep -q 'webgoat/webgoat:2026' docker-compose.qa-targets.yml || fail 'WebGoat image/version is not pinned'

# Guardrail: the prohibited external target must never appear in executable target configuration.
if grep -RniE 'neocapture\.id' --exclude-dir=.git --exclude='*.md' src scripts/qa_target_smoke.sh .github/workflows docker-compose.qa-targets.yml 2>/dev/null; then
  fail 'prohibited target reference detected outside documentation'
fi

# Guardrail: inspect only executable framework paths; this validator's own explanatory text is not a test request.
if grep -RniE '(^|[^A-Za-z])(POST|PUT|PATCH|DELETE)([^A-Za-z]|$)' src scripts/qa_target_smoke.sh .github/workflows 2>/dev/null; then
  fail 'non-read-only HTTP method found in framework execution paths'
fi

echo 'FRAMEWORK_SCOPE_PASS'
echo 'required_files=13'
echo 'docker_targets=2'
echo 'target_network_scope=loopback'
echo 'target_versions=pinned'
echo 'prohibited_target_guard=enabled'
echo 'read_only_guard=enabled'

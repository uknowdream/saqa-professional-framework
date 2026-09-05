#!/usr/bin/env bash
set -euo pipefail

python - <<'PY'
from saqa.jira import verify_from_env

result = verify_from_env()
assert result.key == "QA", f"Unexpected Jira project key: {result.key!r}"
assert result.name, "Jira project name is empty"
print(f"Jira access: PASS (project={result.key}, name={result.name})")
PY

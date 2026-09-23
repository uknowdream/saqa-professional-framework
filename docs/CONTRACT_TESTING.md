# SAQA Contract Testing

Contract testing validates the interface between an API producer and its consumers independently of UI behavior.

## Reference implementation

The framework uses an OpenAPI contract for the authorized local Juice Shop target:

`contracts/juice-shop.openapi.json`

The contract gate:

1. validates the response schema used by the gate;
2. calls the local target with a read-only GET;
3. validates HTTP status and content type;
4. validates the response body against the OpenAPI response schema;
5. emits deterministic JSON evidence.

## Local execution

```bash
make install
docker run --detach --rm --name saqa-juice-shop -p 127.0.0.1:3000:3000 bkimminich/juice-shop:v20.2.0
for attempt in $(seq 1 30); do curl --silent --fail --max-time 3 http://127.0.0.1:3000/ >/dev/null && break; sleep 2; done
python3 scripts/contract_gate.py
docker stop saqa-juice-shop
```

The target is intentionally loopback-only and credential-free.

## CI semantics

A contract failure is a quality failure. An unavailable local target is `BLOCKED`; missing or malformed contract evidence must never become `PASS`.

The contract layer is deliberately independent from Playwright E2E so API interface regressions can fail early and run in parallel.

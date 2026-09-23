# SAQA Contract Mock Service

The mock service is a deterministic, local-only HTTP fixture for validating the contract gate independently of the OWASP Juice Shop runtime.

## Modes

SAQA_MOCK_MODE supports:

- valid — returns a response matching the OpenAPI contract.
- invalid-schema — returns a type mismatch for data[].id.
- missing-data — removes the required data property.
- wrong-content-type — returns JSON with a non-JSON content type.
- malformed-json — returns invalid JSON.
- http-500 — returns HTTP 500.

## Local usage

SAQA_MOCK_MODE=valid SAQA_MOCK_PORT=3100 python scripts/mock_contract_service.py
SAQA_API_BASE_URL=http://127.0.0.1:3100 python scripts/contract_gate.py

The fixture binds only to 127.0.0.1, accepts only GET requests through the standard library server, and has no external network or credential dependencies.

## CI purpose

SAQA Contract Mock Validation proves two properties:

1. a contract-conforming provider produces PASS;
2. a deterministic schema violation produces FAIL rather than being silently accepted.

This is supplemental validation. The release certification domain remains the real authorized Juice Shop contract workflow.

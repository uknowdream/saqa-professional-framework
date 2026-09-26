# SAQA Observability

The observability layer exposes local SAQA evidence as Prometheus metrics and provides a Grafana dashboard.

## Start

Run:
docker compose -f docker-compose.observability.yml up -d

Prometheus is available on http://127.0.0.1:9090 and Grafana on http://127.0.0.1:3001.

The stack is intentionally loopback-only. It reads repository evidence files and does not send test data to external services.

## Metrics

- saqa_quality_status — normalized status per evidence record.
- saqa_quality_evidence_total — number of readable evidence records.

Status values are encoded as PASS=1, FAIL=0, BLOCKED=-1, PENDING=-2, UNVERIFIED=-3. These are telemetry values only; certification remains governed by the fail-closed certification engine.

## Safety

Prometheus and Grafana are bound to loopback addresses. This stack is an observability supplement, not a release-certification authority.

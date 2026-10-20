# Performance regression gate

The local k6 workflow measures the pinned OWASP Juice Shop reference target over loopback. It uses reproducible **versioned guardrails**, not a production SLO or a claim of a statistically stable historical baseline.

## Versioned guardrails

The policy is in \`performance/baselines/juice-shop-local-v1.json\`. Every run records its policy ID/version and measured metrics in commit-specific evidence.

| Metric | Guardrail | Purpose |
| --- | --- | --- |
| HTTP p95 latency | <= 1,000 ms | Tail latency for common requests |
| HTTP p99 latency | <= 1,500 ms | Extreme tail latency |
| HTTP error rate | <= 1% | Request reliability |
| Throughput | >= 1 request/second | Detect severe throughput collapse |
| Functional check pass rate | 100% | Prevent fast but incorrect responses from passing |

The k6 script exports a versioned JSON summary through `handleSummary`, preserving the metric values consumed by the gate rather than depending on the legacy CLI summary serializer. SAQA normalizes p95/p99 latency, error rate, throughput, and check pass rate, evaluates each against the versioned policy, and includes the raw-summary SHA-256 in the evidence. Non-numeric or non-finite measurements and policy limits fail closed. Missing metrics or invalid policy are failures, not silent passes.

## Changing guardrails

Do not tune a limit merely to obtain a green workflow. Record the rationale and evidence, increment the policy version, and review changes alongside the workload and target profile. For statistically meaningful regression detection, collect repeated runs under controlled runner/target conditions and compare distributions; a single CI sample is not sufficient to establish a stable historical baseline.

## Safety and scope

The workload sends only GET requests to the local reference target at \`127.0.0.1:3000\`. It does not test production services and does not perform destructive operations. Throughput should only be compared across runs with the same workload, target version, and comparable environment.

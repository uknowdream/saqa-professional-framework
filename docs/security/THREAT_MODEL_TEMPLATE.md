# SAQA Security Threat Model Template

Use this template for each application or service under test. Blank or incomplete sections mean UNVERIFIED, not risk-free.

## 1. Scope and authorization
- System / repository:
- Owner / security contact:
- Assessment date and version:
- Authorized environments and target URLs:
- Explicitly excluded systems:
- Approval / ticket reference:
- Data classification and handling constraints:

Only test targets with explicit authorization. Keep active security testing isolated from production unless separate documented approval authorizes the exact activity.

## 2. System context
Describe entry points, user roles, trust boundaries, data stores, external services, authentication, authorization, and deployment components. Attach a data-flow diagram when available.

## 3. Assets and security objectives
| Asset | Confidentiality | Integrity | Availability | Owner |
| --- | --- | --- | --- | --- |
| User credentials / tokens | High | High | Medium | TBD |
| Personal or customer data | High | High | Medium | TBD |
| Business records | Medium/High | High | Medium | TBD |
| Service availability | Low | Medium | High | TBD |
| Build artifacts / secrets | High | High | Medium | TBD |

Adjust ratings to the actual system and document the rationale.

## 4. Threat scenarios
For each scenario, record attacker capability, preconditions, affected asset, impact, likelihood, existing controls, test evidence, owner, and residual risk.
- Identity and authentication: credential theft, session fixation, weak recovery, token leakage.
- Authorization: horizontal/vertical privilege escalation, insecure direct object references.
- Input and injection: SQL/command/template injection, unsafe deserialization, path traversal.
- Data protection: sensitive logging, insecure transport, excessive retention, exposure in errors.
- API and integration: missing rate limits, trust-boundary bypass, replay, unsafe webhooks.
- Supply chain: vulnerable dependencies, compromised build inputs, leaked credentials, unpinned actions.
- Deployment/configuration: public debug endpoints, permissive CORS, unsafe defaults, excessive privileges.
- Availability: resource exhaustion, unbounded uploads/queries, dependency failure.

## 5. Risk rating
Use the organization's approved matrix. If none exists, record likelihood and impact separately (Low/Medium/High) and prioritize High impact with plausible exploitability. Do not invent numerical risk scores without a defined method.

## 6. Mitigations and verification
For each accepted risk, specify a mitigation, owner, due date, automated/manual test, evidence reference, and re-test result. A test that was not run or could not access its target must be UNVERIFIED or BLOCKED.

## 7. Exceptions and sign-off
- Exception ID and risk owner:
- Business justification:
- Compensating controls:
- Expiry date (required):
- Approval:
- Retest / closure evidence:

Exceptions must expire and be re-reviewed. A missing owner or expiry date is not a valid permanent exception.

## 8. Exit criteria
- All High risks have a mitigation or an explicitly approved, time-limited exception.
- Evidence is bound to the tested commit/build and target.
- Unrun tests remain clearly marked UNVERIFIED.
- Residual risks are accepted by the named owner.
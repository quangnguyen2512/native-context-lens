---
id: release-readiness-checklist
collection: launch_blockers
kind: review
title: "Q4 GA Release Readiness Checklist"
status: blocked
owner: "Devon Brooks (Staff Infra)"
updated_at: 2026-09-30T13:15:00Z
summary: "GA launch checklist with 9/10 gates green; offline sync scalability still cites v1 architecture spec."
facets: {"track": ["q4_launch"], "quarter": ["Q4"], "priority": ["P0"]}
links: [{"relation": "references", "target": "mobile-sync-architecture-v1", "note": "Sync reliability sign-off originally mapped to v1 polling architecture"}]
---

# Q4 GA Release Readiness Checklist

## Gate Status (9 of 10 Complete)
- [x] Deterministic event-log replay test passes across 100% of beta workspace backups
- [x] MCP stdio server cold-start latency < 45ms on macOS, Linux, and Windows
- [x] Malleable artifact sandbox CSP + fail-closed capability audit green
- [x] Billing webhooks & seat metering reconciliation verified
- [x] Crash reporting & OpenTelemetry redaction verified (zero PII/content leakage)
- [x] Automated rollback runbook rehearsed in staging
- [ ] **BLOCKED: Offline Multi-Client Sync Reliability under 50k concurrent connections**

## Referenced Sync Spec
The remaining unchecked gate was originally scoped against [[mobile-sync-architecture-v1]], targeting 5,000 concurrent reconnecting clients using periodic HTTP checkpoint polling.

## Engineering Notes
- Beta telemetry revealed burst reconnect storms (Monday 09:00 UTC + flight landings) create 8x higher write contention than steady-state averages.
- API deprecation impact on legacy beta clients is tracked in [[api-v1-deprecation]].
- Infra team needs finalized benchmark certification against the updated sync design before checking off the final GA box and lifting [[q4-launch-freeze]].

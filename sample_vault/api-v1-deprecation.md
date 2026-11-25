---
id: api-v1-deprecation
collection: launch_blockers
kind: deprecation
title: "API v1 Deprecation & Sunset Notice"
status: blocked
owner: "Hannah Cho (DX Lead)"
updated_at: 2026-10-04T11:45:00Z
summary: "Formal 90-day API v1 sunset email and header rollout blocked on enterprise migration tracker."
facets: {"track": ["api_v1"], "quarter": ["Q4"], "priority": ["P1"]}
links: [{"relation": "depends_on", "target": "enterprise-migration-tracker", "note": "Cannot broadcast sunset clock until migration path & SDK timeline are locked"}]
---

# API v1 Deprecation & Sunset Notice

## Overview
Native API v1 (untyped JSON document blobs without explicit collection envelopes or fail-closed capability tokens) accounts for 14% of legacy beta traffic but incurs 40% of support maintenance overhead. Developer Experience plans to emit RFC 8594 `Deprecation` / `Sunset` HTTP headers and email all active API key owners starting this month.

## Gating Dependency
Publishing the formal sunset clock is gated on [[enterprise-migration-tracker]] because 7 design-partner teams (including Northwind Logistics's warehouse sync pilot in [[northwind-deal]]) still have scripts targeting `/v1/docs` endpoints.

## Customer Communication Plan
- Automated email notice with per-workspace breakdown of active v1 endpoints called over the last 30 days.
- Interactive codemod script (`npx native-migrate-v2`) converting legacy payload schemas to `native.collection-envelope.v1`.
- Dedicated `#api-migration` Discord office hours run by Builder-in-Residence and DX engineers.

## Open Risk
Announcing a fixed sunset date before our official Python and TypeScript v3 SDKs ship creates developer friction and forces teams to hand-roll raw HTTP clients — violating our strict developer-first standard.

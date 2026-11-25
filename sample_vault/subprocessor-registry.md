---
id: subprocessor-registry
collection: launch_blockers
kind: review
title: "Tier-1 Subprocessor Registry & DPA Tracker"
status: blocked
owner: "Nadia Kowalski (Compliance Ops)"
updated_at: 2026-09-24T09:45:00Z
summary: "Master list of 12 Tier-1 subprocessors still referencing Q2 vendor DPA template for Helios EU."
facets: {"track": ["soc2"], "quarter": ["Q4"], "priority": ["P1"]}
links: [{"relation": "references", "target": "vendor-dpa-2026-q2", "note": "Helios EU storage row currently cites Q2 DPA terms"}]
---

# Tier-1 Subprocessor Registry & DPA Tracker

## Purpose
Central inventory of all third-party processors touching customer metadata, encrypted backups, transactional email, or model inference gateways. Reviewed quarterly by Compliance and Legal prior to publishing updates to `withnative.ai/trust`.

## Tier-1 Inventory Snapshot
| Vendor | Region | Data Category | DPA Status |
|---|---|---|---|
| AWS (us-west-2, eu-central-1) | US / EU | Primary compute & KMS | Executed 2026-01 |
| Cloudflare | Global | Edge routing & DDoS | Executed 2026-02 |
| Postmark | US | Auth & notification mail | Executed 2026-03 |
| Helios Cloud Storage GmbH | EU (Frankfurt) | Encrypted regional replicas | **Hold — cites [[vendor-dpa-2026-q2]]** |

## Open Gap
Helios Cloud Storage GmbH handles zero-knowledge encrypted SQLite snapshot replicas for European customers requiring Frankfurt data residency. The registry entry currently links to [[vendor-dpa-2026-q2]], which predated our updated incident notification SLA (24h vs 72h) and mutual liability cap language.

## Review Notes
- Infra confirmed Helios bucket policies enforce customer-managed envelope encryption and strict EU residency tags.
- Annual vendor penetration report from Helios (ISO 27001 + BSI C5) passed security review with zero critical findings.
- Waiting on Legal confirmation of the final Helios DPA artifact so Compliance can clear CC9.2 in [[soc2-vendor-approval]].

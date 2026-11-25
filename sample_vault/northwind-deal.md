---
id: northwind-deal
collection: launch_blockers
kind: deal
title: "Northwind Logistics Enterprise Deal ($420k ARR)"
status: blocked
owner: "Maya Lin (Enterprise AE)"
updated_at: 2026-10-04T15:30:00Z
summary: "3-year $420k ARR Northwind Logistics expansion blocked on revised multi-year pricing review."
facets: {"track": ["northwind"], "quarter": ["Q4"], "priority": ["P0"]}
links: [{"relation": "depends_on", "target": "pricing-review", "note": "Requires finalized multi-year discount floor before order form issue"}]
---

# Northwind Logistics Enterprise Deal ($420k ARR)

## Executive Context
Northwind Logistics (1,450 seats across North America and EMEA freight hubs) completed a 45-day technical pilot with 94% weekly active adoption across dispatch, operations, and finance teams. Procurement redlines on the Master Subscription Agreement closed on September 28, leaving commercial order-form pricing as the sole gating item before signature.

## Deal Desk Status & Dependencies
- Commercial structure is currently gated on [[pricing-review]] because Northwind requested a 3-year commit with an 18% blended volume discount and ramped seat commits in Year 1.
- Their platform engineering lead also asked whether their warehouse integration is impacted by the deprecation schedule tracked in [[enterprise-migration-tracker]] and [[soc2-vendor-approval]].
- Customer champion (VP Ops, Carla Mendez) confirmed budget lock expires October 16; slipping past that date pushes recognition into Q1.

## Pilot Telemetry & Usage Notes
During the 6-week pilot, Northwind imported 11,400 shipment SOPs, vendor exception logs, and customs runbooks into a shared workspace. Average ticket triage time dropped from 26 minutes to 4.8 minutes when agents queried structured tables instead of raw wiki pages. Peak concurrency reached 620 simultaneous editors during Monday morning hub dispatch without sync conflicts.

## Stakeholder Call Log
- **2026-09-18 (Discovery Recap):** CFO office flagged payment terms (Net 45 vs Net 30) and asked for multi-year price-lock cap at 4% CPI uplift upon renewal.
- **2026-09-25 (Security Questionnaire):** Passed initial SIG Lite review pending final attestation link from [[enterprise-security-audit]].
- **2026-10-03 (Commercial Check-in):** Procurement confirmed paper is clean; awaiting updated Order Form #NW-2026-04 once our internal pricing review clears.
- **2026-10-04 (Deal Desk Escalation):** Maya escalated to RevOps because the spreadsheet attached to the September review still reflected the old Q3 discount bands rather than October's revised enterprise policy.

## Open Commercial Action Items
1. Confirm exact approved multi-year discount ceiling via [[pricing-review]].
2. Attach finalized 36-month payment schedule and ramp addendum ($110k Y1 / $145k Y2 / $165k Y3).
3. Verify onboarding kickoff slot with Solutions Architecture once order form is countersigned.
4. Keep weekly deal desk notes synchronized so forecasting reflects accurate close confidence and approval dependencies.
5. Prepare joint executive launch brief covering regional warehouse teams in Rotterdam, Chicago, Memphis, and Singapore once signature clears.

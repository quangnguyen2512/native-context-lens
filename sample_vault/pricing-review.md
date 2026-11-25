---
id: pricing-review
collection: launch_blockers
kind: review
title: "Q4 Enterprise Multi-Year Pricing Review"
status: blocked
owner: "Samir Patel (RevOps Lead)"
updated_at: 2026-10-01T11:20:00Z
summary: "Commercial desk pricing review for >1,000-seat deals referencing September discount policy."
facets: {"track": ["northwind"], "quarter": ["Q4"], "priority": ["P0"]}
links: [{"relation": "references", "target": "decision-2026-09-12", "note": "Initial pricing model built against September discount floor"}]
---

# Q4 Enterprise Multi-Year Pricing Review

## Review Scope
This review evaluates enterprise multi-year unit economics, seat ramp concessions, and implementation fee waivers for strategic deals above $250k ARR (starting with Northwind Logistics and two healthcare prospects in late-stage legal review).

## Policy Baseline Referenced
Our initial margin model and CPQ approval worksheet were calibrated directly against [[decision-2026-09-12]], which established the Q3 commercial discount bands and AE self-serve thresholds. Under that worksheet, any multi-year discount above 12% triggers executive deal desk sign-off and custom gross-margin verification.

## Margin & Unit Economics Breakdown
- Standard Enterprise list price: $36/seat/month billed annually ($432/seat/year).
- Hosted agent compute COGS at p90 workload: $4.10/seat/month including SQLite replication, embeddings, and artifact sandbox telemetry.
- Proposed Northwind blended net price at 18% discount: $29.52/seat/month, preserving 86.1% gross margin over the 36-month term provided implementation services ($28k) remain unbundled.
- Cash collection impact: Net 45 billing adds 15 days DSO but annual upfront invoicing yields +$110k immediate Q4 cash inflow.

## Cross-Functional Review Notes
- **RevOps (Samir):** CPQ guardrails currently hard-block quote generation above 12% unless an exception ID is entered. Waiting on final policy confirmation before issuing Northwind Order Form #NW-2026-04.
- **Solutions Architecture:** Confirmed deployment requires zero bespoke infra; standard tenant provisioning aligns with [[release-readiness-checklist]].
- **Customer Success:** Requested that any discount above 15% include a mandatory executive business review cadence and public anonymized case study rights after 90 days in production.

## Historical Scenarios Considered
1. Option A (10% discount + 3 months free): Effective discount 17.5%, complicates ARR recognition and renewal uplift math.
2. Option B (15% flat discount + waived onboarding): Leaves $18k gap vs customer budget ceiling.
3. Option C (18% multi-year discount floor with 3-year non-cancellable lock + 5% renewal cap): Best alignment with procurement mandate, pending formal executive policy sign-off.
4. Option D (Usage-tiered seat floor with burst compute overage): Rejected by Northwind procurement due to unpredictable freight seasonality.

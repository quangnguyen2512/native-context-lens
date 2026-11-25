---
id: enterprise-migration-tracker
collection: launch_blockers
kind: review
title: "Enterprise API v1 -> v2 Migration Tracker"
status: blocked
owner: "Hannah Cho (DX Lead)"
updated_at: 2026-09-26T15:00:00Z
summary: "Tracks 7 design-partner migrations off API v1; schedule still links to superseded draft timeline."
facets: {"track": ["api_v1"], "quarter": ["Q4"], "priority": ["P1"]}
links: [{"relation": "references", "target": "deprecation-timeline-draft", "note": "Customer milestone dates currently mirror original draft schedule"}]
---

# Enterprise API v1 -> v2 Migration Tracker

## Partner Migration Matrix
| Workspace | Daily v1 Calls | Target API v2 Cutover | Blocker / Status |
|---|---|---|---|
| Northwind Pilot | 18,400 | Nov 15 | Awaiting Python SDK v3 typed client |
| Meridian Labs | 9,200 | Nov 01 | Migrated 80% in staging |
| Cobalt Freight | 6,150 | Nov 20 | Waiting on TypeScript webhook verifier |
| Harbor Bio | 4,300 | Oct 28 | Ready for cutover |
| 3 smaller beta teams | 2,900 | Nov 10 | Auto-migrated via codemod |

## Referenced Schedule
Partner outreach emails sent in mid-September referenced [[deprecation-timeline-draft]], which projected a 60-day shutdown window ending November 30 without waiting for unified SDK v3 bindings.

## Support Feedback
Design partners pushed back strongly during September check-ins: maintaining custom raw-fetch wrappers for governed collection envelopes is brittle, and they asked for first-class typed Python & TypeScript SDK packages with built-in retry, ACL error handling, and MCP schema parity before their migration clock starts ticking.

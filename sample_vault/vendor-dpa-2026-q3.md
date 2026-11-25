---
id: vendor-dpa-2026-q3
collection: launch_blockers
kind: decision
title: "Vendor DPA Template 2026-Q3 (24h SLA + EU SCC Annex II)"
status: blocked
owner: "Marcus Reid (General Counsel)"
updated_at: 2026-09-28T17:45:00Z
summary: "Supersedes vendor-dpa-2026-q2 with 24h breach notice & 3x super-cap; pending GC redline sign-off."
facets: {"track": ["soc2"], "quarter": ["Q4"], "priority": ["P0"]}
links: [{"relation": "supersedes", "target": "vendor-dpa-2026-q2", "note": "Upgrades Tier-1 subprocessor SLA to 24h notice and 3x confidentiality super-cap"}, {"relation": "waiting_on", "target": "legal-redline-signoff", "note": "Awaiting final GC approval of Helios Annex II liability cap redline"}]
---

# Vendor DPA Template 2026-Q3 (24h SLA + EU SCC Annex II)

## Supersession Notice
This mandatory Tier-1 DPA baseline **supersedes [[vendor-dpa-2026-q2]]** for all storage and replication subprocessors handling enterprise workspace data.

## Key Upgrades Over Q2 Template
- **24-Hour Breach Notice:** Tightened from 72 hours to 24 hours so Native can honor 48-hour enterprise customer notification SLAs.
- **3x Super-Cap:** Dedicated 3x annual fees liability super-cap for unauthorized disclosure or EU residency violation.
- **Explicit Annex II Encryption Controls:** Requires documented key isolation matching our zero-trust security posture in [[enterprise-security-audit]].

## Current Blocker
Helios Cloud Storage GmbH accepted the 24-hour notice SLA and Annex II encryption controls, but returned one redline on Section 8.2 (capping super-cap liability at 2.5x annual fees or $500k minimum). Execution is **waiting on [[legal-redline-signoff]]** from General Counsel before countersignature.

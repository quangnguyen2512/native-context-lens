---
id: legal-redline-signoff
collection: launch_blockers
kind: signoff
title: "Legal Redline Sign-Off: Helios DPA Annex II & 2.5x Super-Cap"
status: pending_signoff
owner: "Marcus Reid (General Counsel)"
updated_at: 2026-10-04T16:20:00Z
summary: "Internal General Counsel approval pending on Helios $500k floor / 2.5x confidentiality super-cap redline."
facets: {"track": ["soc2"], "quarter": ["Q4"], "priority": ["P0"], "classification": ["internal_only"]}
links: [{"relation": "blocks", "target": "vendor-dpa-2026-q3", "note": "Helios DPA cannot be countersigned until GC approves Section 8.2 compromise"}]
allowed_roles: ["founder", "member"]
---

# Legal Redline Sign-Off: Helios DPA Annex II & 2.5x Super-Cap

## Internal Legal Privilege Notice
Restricted to internal team members and founders (excluded from external contractors).

## Blocking Status
**PENDING GC SIGN-OFF** — Marcus Reid is reviewing outside EU privacy counsel's memo on whether accepting Helios's counter-proposal (`MAX(2.5x annual fees, $500,000)` super-cap) exposes any contractual gap against our enterprise customer MSA caps. This directly blocks [[vendor-dpa-2026-q3]] execution and downstream SOC 2 CC9.2 clearance.

## Redline Assessment
- Annual Helios spend is projected at $84k in Year 1; thus the $500k hard floor actually provides **5.95x coverage**, exceeding our standard 3x requirement.
- Annex II technical safeguards (envelope encryption + Frankfurt-only replication + 24h incident notification) were accepted verbatim without modification.
- Cyber insurance broker confirmed $500k vendor floor satisfies policy subrogation requirements.

## Expected Resolution
Outside counsel sign-off expected October 6 morning; Marcus will countersign via DocuSign and notify Compliance to clear [[soc2-vendor-approval]].

---
id: soc2-vendor-approval
collection: launch_blockers
kind: compliance
title: "SOC 2 Type II Vendor & Subprocessor Approval Gate"
status: blocked
owner: "Nadia Kowalski (Compliance Ops)"
updated_at: 2026-10-04T12:00:00Z
summary: "SOC 2 observation window sign-off blocked on updated EU subprocessor DPA redlines."
facets: {"track": ["soc2"], "quarter": ["Q4"], "priority": ["P0"]}
links: [{"relation": "depends_on", "target": "subprocessor-registry", "note": "Auditor requires executed DPAs for 100% of Tier-1 subprocessors"}]
---

# SOC 2 Type II Vendor & Subprocessor Approval Gate

## Compliance Readiness Summary
Our SOC 2 Type II audit firm (Vanta + Prescient Assurance) completed control sampling for Security, Availability, and Confidentiality trust principles. All 47 automated infrastructure monitors are green, leaving CC9.2 (Vendor Risk Management — executed subprocessor Data Processing Agreements) as the single open exception blocking the draft report.

## Dependency Chain
- Auditor evidence pack pulls directly from [[subprocessor-registry]], which maps every Tier-1 infrastructure vendor handling encrypted workspace snapshots, telemetry, or AI inference routing.
- Enterprise prospects (including Northwind Logistics in [[northwind-deal]]) also review our live Trust Center subprocessor matrix prior to contract execution.

## Audit Sampling Findings
- 11 of 12 Tier-1 subprocessors have countersigned 2026 DPAs, current SOC 2 Type II reports, and verified encryption-at-rest attestations on file.
- 1 Tier-1 EU replication vendor (`Helios Cloud Storage GmbH`) still shows an expired Q2 template link in the compliance tracker, triggering an automatic auditor hold under control CC9.2.

## Next Steps
1. Verify latest executed DPA revision inside [[subprocessor-registry]].
2. Upload countersigned PDF and EU Standard Contractual Clauses (SCCs) into Prescient evidence portal.
3. Obtain final compliance closure before the October 15 observation cutoff so enterprise trust packet ships on time.

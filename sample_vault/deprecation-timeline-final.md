---
id: deprecation-timeline-final
collection: launch_blockers
kind: decision
title: "API v1 Deprecation Policy Final (90-Day Post-SDK-v3 Window)"
status: blocked
owner: "Hannah Cho (DX Lead) & Richard"
updated_at: 2026-10-03T16:10:00Z
summary: "Supersedes deprecation-timeline-draft: 90-day sunset clock starts ONLY after sdk-v3-release-gate ships."
facets: {"track": ["api_v1"], "quarter": ["Q4"], "priority": ["P1"]}
links: [{"relation": "supersedes", "target": "deprecation-timeline-draft", "note": "Extends grace period to 90 days gated strictly on SDK v3 GA release"}, {"relation": "waiting_on", "target": "sdk-v3-release-gate", "note": "Sunset countdown cannot start until Python + TypeScript SDK v3.0 GA cut"}]
---

# API v1 Deprecation Policy Final (90-Day Post-SDK-v3 Window)

## Supersession Notice
This finalized policy **supersedes [[deprecation-timeline-draft]]**. The aggressive 60-day raw-HTTP cutoff is cancelled.

## Customer-First Deprecation Rule
Native commits to a strict **90-day migration clock that starts ONLY after GA publication** of both official `native-sdk` TypeScript (`npm`) and Python (`PyPI`) v3.0 packages with full typed support for `native.collection-envelope.v1`, caller ACL errors, and recursive link queries.

## Current Blocker
Policy terms and partner comms are approved, but sending the formal sunset notice in [[api-v1-deprecation]] is **waiting on [[sdk-v3-release-gate]]** to cut and verify SDK v3.0.0 GA artifacts.

## Revised Milestones (T = SDK v3.0 GA Date)
- **T + 0 days:** Publish SDK v3.0.0 GA + migration codemod + official 90-day deprecation email.
- **T + 45 days:** Soft reminder + automated PR helper for remaining v1 partners.
- **T + 90 days:** Sunset `/v1/*` routes cleanly with zero broken enterprise pilots.

---
id: sdk-v3-release-gate
collection: launch_blockers
kind: gate
title: "SDK v3.0 GA Release Gate (Python & TypeScript Packages)"
status: pending_signoff
owner: "Hannah Cho (DX Lead)"
updated_at: 2026-10-04T19:00:00Z
summary: "Final CI signing, PyPI/npm dry-run, and contract test sign-off for Python & TypeScript SDK v3.0 GA."
facets: {"track": ["api_v1"], "quarter": ["Q4"], "priority": ["P1"]}
links: [{"relation": "blocks", "target": "deprecation-timeline-final", "note": "90-day deprecation clock cannot start until SDK v3.0 GA is published"}]
---

# SDK v3.0 GA Release Gate (Python & TypeScript Packages)

## Release Gate Status
**PENDING RELEASE CUT** — Python (`native-sdk==3.0.0rc4`) and TypeScript (`@withnative/sdk@3.0.0-rc.4`) release candidates are feature-complete; waiting on final contract conformance pass and Sigstore provenance signing. This gate directly blocks [[deprecation-timeline-final]] and [[api-v1-deprecation]].

## Remaining Pre-GA Checklist
1. **Cross-Language Contract Suite:** Verify 100% parity on fail-closed `403 AuthorizationError` deserialization and `native.collection-envelope.v1` pagination cursors across Python 3.11-3.13 and Node 20-22.
2. **Idempotent Retry Guards:** Confirm automatic exponential backoff never duplicates non-idempotent event appends (client-generated `event_id` deduplication check).
3. **PyPI Trusted Publisher + npm Provenance:** Cut signed release tags via GitHub Actions OIDC with zero manual token handling.
4. **Docs & Quickstart Smoke Test:** Verify 5-minute quickstart snippets pass end-to-end against local Native MCP stdio server.

## Target Release Date
Scheduled for October 7 once the final TypeScript ESM/CJS dual-package smoke test merges.

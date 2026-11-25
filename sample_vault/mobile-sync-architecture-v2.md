---
id: mobile-sync-architecture-v2
collection: launch_blockers
kind: decision
title: "Mobile & Desktop Sync Architecture v2 (Batched WAL Delta Streams)"
status: blocked
owner: "Devon Brooks (Staff Infra)"
updated_at: 2026-10-02T10:05:00Z
summary: "Supersedes mobile-sync-architecture-v1 with batched WAL delta streams; waiting on load-test-certification."
facets: {"track": ["q4_launch"], "quarter": ["Q4"], "priority": ["P0"]}
links: [{"relation": "supersedes", "target": "mobile-sync-architecture-v1", "note": "Replaces 5s HTTP polling with batched WebSocket/SSE WAL delta coalescing"}, {"relation": "waiting_on", "target": "load-test-certification", "note": "Requires passing 50k concurrent client 12-hour soak test"}]
---

# Mobile & Desktop Sync Architecture v2 (Batched WAL Delta Streams)

## Supersession Notice
This architecture **supersedes [[mobile-sync-architecture-v1]]**. HTTP single-event polling is replaced by batched WAL delta streams and single-writer group commit coalescing.

## Key Engineering Improvements
- **Group Commit Coalescing:** Server batches up to 64 inbound client mutations into one `BEGIN IMMEDIATE` SQLite WAL transaction every 15ms, cutting write lock contention by 94%.
- **Long-Lived Delta Push:** Server pushes compact binary event deltas over multiplexed WebSocket/HTTP2 streams, eliminating 5-second idle poll chatter.
- **Deterministic Conflict-Free Replay:** Client receives authoritative server `seq` ordering and replays derived projections atomically in <8ms.

## Current Blocker
Implementation merged to `main` on October 2, and unit/chaos suites are green, but GA sign-off is **waiting on [[load-test-certification]]** (50,000 simulated concurrent clients + reconnect storm soak test for 12 continuous hours).

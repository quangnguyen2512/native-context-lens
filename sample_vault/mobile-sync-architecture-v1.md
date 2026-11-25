---
id: mobile-sync-architecture-v1
collection: launch_blockers
kind: decision
title: "Mobile & Desktop Sync Architecture v1 (HTTP Checkpoint Polling)"
status: active
owner: "Devon Brooks (Staff Infra)"
updated_at: 2026-08-20T11:30:00Z
summary: "August v1 sync design using 5-second HTTP checkpoint polling with per-client SQLite write locks."
facets: {"track": ["q4_launch"], "quarter": ["Q3"], "priority": ["P1"]}
links: []
---

# Mobile & Desktop Sync Architecture v1 (HTTP Checkpoint Polling)

## Architectural Summary (Approved 2026-08-20)
Version 1 of Native's offline sync protocol synchronizes client event logs via stateless HTTP POST/GET checkpoint polling every 5 seconds (`GET /sync/events?after_seq=N`).

## Mechanism
1. Each client maintains a local SQLite WAL replica of workspace events and derived projections.
2. Offline mutations append to a local pending outbox queue.
3. On reconnect, the client POSTs pending events one-by-one and polls for remote `seq` advances every 5 seconds.
4. Server acquires a workspace-level `BEGIN IMMEDIATE` write lock per individual event POST.

## Strengths in Early Beta
- Extremely simple to debug with curl and standard HTTP proxies.
- Worked reliably up to ~200 concurrent teams and ~1,500 active devices.

## Scaling Bottlenecks Observed
- Under burst reconnects (200+ events queued per device), sequential single-event HTTP POSTs created lock-wait queues exceeding 4 seconds (`SQLITE_BUSY` retries).
- 5-second polling across idle mobile apps generated 78% wasted empty-delta requests, inflating edge bandwidth costs.

---
id: auth-token-rotation-rfc
collection: launch_blockers
kind: decision
title: "RFC-019: Symmetric Dual-HMAC Token Rotation (v1)"
status: active
owner: "Liam O'Connor (Backend Staff)"
updated_at: 2026-09-14T10:00:00Z
summary: "Initial September RFC proposing dual-secret HMAC-SHA256 rotation via encrypted env vars."
facets: {"track": ["security"], "quarter": ["Q3"], "priority": ["P1"]}
links: []
---

# RFC-019: Symmetric Dual-HMAC Token Rotation (v1)

## Decision Summary (Approved 2026-09-14)
This RFC specifies a lightweight dual-key HMAC-SHA256 signing scheme (`PRIMARY_SIGNING_SECRET`, `SECONDARY_SIGNING_SECRET`) allowing rolling 30-day secret rotation without forcing active users to re-authenticate.

## Design Overview
1. Every token header includes `kid` (`hmac-2026-09`, `hmac-2026-10`).
2. Auth gateway signs newly minted tokens exclusively with `PRIMARY_SIGNING_SECRET`.
3. Verification accepts both primary and secondary secrets during a 24-hour drain window, after which the secondary secret is purged from deployment config.
4. Secrets are injected at container boot from cloud Secrets Manager and rotated via CI scheduled workflow.

## Why Symmetric Was Initially Chosen
- Sub-microsecond verification latency in Rust and Python runtimes.
- Zero external KMS RPC hops during hot-path token validation.
- Minimal operational complexity for self-hosted Docker deployments where customers may not operate an enterprise HSM.

## Trade-offs Noted at Authoring
- Every verifying microservice holds the signing key, expanding blast radius if a read-only edge worker is compromised.
- Does not produce hardware-backed non-exportable audit proofs if an auditor demands FIPS 140-3 Level 3 root custody.
- Revisit asymmetric Ed25519 delegation only if enterprise penetration auditors flag shared worker verification secrets.

---
id: auth-token-rotation-v2
collection: launch_blockers
kind: decision
title: "RFC-019 v2: Asymmetric Ed25519 + HSM Root Rotation"
status: blocked
owner: "Priya Nair (Security Lead)"
updated_at: 2026-10-01T19:00:00Z
summary: "Supersedes auth-token-rotation-rfc with asymmetric Ed25519 signing; pending root trust ceremony."
facets: {"track": ["security"], "quarter": ["Q4"], "priority": ["P0"]}
links: [{"relation": "supersedes", "target": "auth-token-rotation-rfc", "note": "Replaces shared HMAC secrets with non-exportable HSM-rooted Ed25519 keys"}, {"relation": "waiting_on", "target": "kms-key-ceremony", "note": "Production root keypair cannot be minted until 2-of-3 founder HSM ceremony"}]
---

# RFC-019 v2: Asymmetric Ed25519 + HSM Root Rotation

## Supersession Notice
This specification **supersedes [[auth-token-rotation-rfc]]**. Following TrailBit's formal feedback on `TB-2026-04`, shared symmetric HMAC secrets are deprecated for cloud-hosted multi-tenant deployments.

## Revised Architecture
- **Signing Plane:** Only the isolated Auth Mint service can request Ed25519 child key delegation certificates signed by a FIPS 140-3 HSM root key.
- **Verification Plane:** Edge relays and MCP servers cache only public JWKS keys (`EdDSA`), completely eliminating signing-secret exposure in worker RAM.
- **Rotation Cadence:** Automated 14-day leaf key rotation with 60-second emergency CRL propagation across all workspace nodes.

## Current Blocker
Code implementation and staging unit tests are 100% merged, but production deployment is **waiting on [[kms-key-ceremony]]** to mint the initial production HSM root trust anchor under 2-of-3 custodian quorum.

## Verification Checklist
- Public JWKS endpoint verified at <0.4ms p99 verification latency.
- Self-hosted open-source mode continues to support local Ed25519 file keys out of the box with zero cloud dependency.
- Once [[kms-key-ceremony]] completes, staging evidence and production root fingerprint will be delivered to TrailBit to close [[pentest-remediation-plan]] and [[enterprise-security-audit]].

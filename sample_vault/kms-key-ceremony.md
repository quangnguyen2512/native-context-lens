---
id: kms-key-ceremony
collection: launch_blockers
kind: signoff
title: "Hardware HSM Root Key Ceremony (2-of-3 Quorum)"
status: pending_signoff
owner: "Priya Nair & Founders (Quorum)"
updated_at: 2026-10-04T19:30:00Z
summary: "Founder-only 2-of-3 hardware YubiKey quorum ceremony required to initialize production Ed25519 HSM root."
facets: {"track": ["security"], "quarter": ["Q4"], "priority": ["P0"], "classification": ["founder_only"]}
links: [{"relation": "blocks", "target": "auth-token-rotation-v2", "note": "Production HSM root key cannot be activated without 2-of-3 physical custodian ceremony"}]
allowed_roles: ["founder"]
---

# Hardware HSM Root Key Ceremony (2-of-3 Quorum)

## Restricted Governance Notice (Founder / Security Custodians Only)
This operational runbook governs physical YubiKey smart-card shares, air-gapped recovery shards, and production KMS root attestation parameters. Access is strictly restricted to founders.

## Blocking Status
**PENDING EXECUTION** — Production rollout of [[auth-token-rotation-v2]] is blocked until two of three designated custodians (George, Richard, Priya) complete the witness-logged CloudHSM initialization ceremony.

## Ceremony Protocol
1. Verify fresh tamper-evident seals on custodian hardware tokens #01, #02, and #03.
2. Execute `hsm-bootstrap --curve ed25519 --non-exportable --quorum 2-of-3` inside clean ephemeral bastion with deterministic audit log recording.
3. Export ONLY the public root certificate (`root-ed25519-2026.pub`) and SHA-256 fingerprint into the signed deployment manifest.
4. Store offline recovery shards in separate geographically distributed safe deposit boxes and sign the witness attestation ledger.

## Schedule
Ceremony window scheduled for October 7 at 17:00 UTC once Richard returns from London customer visits. Completion unlocks production key minting and closes `TB-2026-04`.

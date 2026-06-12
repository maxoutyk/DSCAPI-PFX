# IG E-Sign USB DSC Agent — Design Spec

**Date:** 2026-06-10  
**Status:** Phase D foundation implemented on `feature/usb-dsc-agent`  
**Branch target:** merge to `master` when PKCS#11 installer is ready

## Goal

Sign PDFs with a **USB DSC token** while keeping cloud orchestration, audit, and quotas on the existing tenant account.

## Architecture (Option A)

| Component | Responsibility |
|-----------|----------------|
| **Portal** (existing login) | Pair agents, upload PDF, trigger local sign, download |
| **Cloud API** | Prepare placement, store job, complete audit (`endpoint=sign-usb`) |
| **Desktop agent** (separate installer) | PKCS#11 + PIN, localhost bridge, heartbeats |

Private keys never leave the USB token. Cloud stores prepared PDF bytes encrypted until the agent completes signing.

## Portal (same tenant login)

- `/dashboard/agent/` — pair code, device list (online/offline), revoke
- `/dashboard/sign/usb/` — upload PDF → pending → done → download
- Sidebar: **USB Sign**, **USB Agent**

## Agent API

| Endpoint | Auth | Purpose |
|----------|------|---------|
| `POST /api/agent/pair/` | Pairing code | Register device, return `dsc_agent_*` token |
| `POST /api/agent/heartbeat/` | Device token | Last seen, version, token/cert metadata |
| `GET /api/agent/jobs/<id>/` | Device token | Fetch prepared PDF + placement |
| `POST /api/agent/jobs/<id>/complete/` | Device token | Upload signed PDF |

## Data model (`usb_agent` app)

- `AgentDevice` — paired machine per tenant
- `AgentPairingCode` — 6-digit TTL code from portal session
- `UsbSignJob` — prepare/complete lifecycle, encrypted PDF at rest

## Desktop agent (`desktop-agent/`)

Development stub with:

- `pair` / `run` CLI
- `GET /health`, `POST /sign` on `127.0.0.1:9765`
- Dev signing via `IG_AGENT_DEV_PFX_*` until PKCS#11 ships

Production: Windows installer, PKCS#11 (eMudhra et al.), auto-update.

## Deferred

- PKCS#11 production signing
- Windows installer / code signing
- Token insert/remove events
- Agent auto-update channel

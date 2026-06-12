# IG E-Sign Desktop Agent (development stub)

Separate installer package for USB DSC token signing. This folder contains a **development stub** — production builds will add PKCS#11 and a Windows installer.

## Pair with your tenant

1. Log in to the portal → **USB Agent** → **Generate pairing code**
2. Run:

```bash
python desktop-agent/agent.py pair --api-base http://localhost --code 123456
```

## Run local agent

```bash
export IG_AGENT_DEV_PFX_PATH=/path/to/cert.pfx
export IG_AGENT_DEV_PFX_PASSWORD=your-pin
python desktop-agent/agent.py run --port 9765
```

Until PKCS#11 is implemented, dev signing uses the PFX env vars above (same placement as cloud prepare).

## Portal flow

1. **USB Sign** → upload PDF
2. Browser calls local agent on `127.0.0.1:9765`
3. Agent fetches job from `/api/agent/jobs/<id>/`, signs, completes
4. Download signed PDF from portal

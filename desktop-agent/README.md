# IG E-Sign Desktop Agent (development stub)

Separate installer package for USB DSC token signing. This folder contains a **development stub** — production builds will add PKCS#11 and a Windows installer.

## Download from portal

1. Log in to IG E-Sign → **USB Agent**
2. Click **Download for Windows (.exe)** or **Download agent package (ZIP)**
3. Windows installer: launch **IG E-Sign Agent**, pair from the app window, then sign from the portal. Closing the window keeps the agent in the tray.
4. ZIP (dev/macOS/Linux): extract and run `start-agent.bat` or `start-agent.sh`

The Windows installer includes `portal.url` with the live portal address preconfigured.

## Build Windows installer (.exe)

Requires **Windows** + [Inno Setup 6](https://jrsoftware.org/isinfo.php):

```powershell
powershell -ExecutionPolicy Bypass -File build\windows\build-agent.ps1
```

Output: `desktop-agent/releases/IG-E-Sign-Agent-Setup.exe`

Deploy to the server:

```bash
USB_AGENT_INSTALLER_PATH=/opt/dscapi/desktop-agent/releases/IG-E-Sign-Agent-Setup.exe
```

Or copy the file into `desktop-agent/releases/` on the app host — the portal serves it automatically when present.

GitHub Actions: **Build IG E-Sign Agent (Windows)** workflow (manual dispatch).

## Pair manually (developers)

1. Log in to the portal → **USB Agent** → **Generate pairing code**
2. Run:

```bash
python desktop-agent/agent.py pair --api-base http://localhost --code 123456
```

## Run local agent

```bash
export IG_AGENT_DEV_PFX_PATH=/path/to/cert.pfx
export IG_AGENT_DEV_PFX_PASSWORD=your-pin
python desktop-agent/agent.py run --port 9765          # Windows: system tray
python desktop-agent/agent.py run --port 9765 --console  # terminal mode
```

Until PKCS#11 is implemented, dev signing uses the PFX env vars above (same placement as cloud prepare).

## Portal flow

1. **USB Sign** → upload PDF
2. Browser calls local agent on `127.0.0.1:9765`
3. Agent fetches job from `/api/agent/jobs/<id>/`, signs, completes
4. Download signed PDF from portal

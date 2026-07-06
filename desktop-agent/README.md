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

GitHub Actions: **Build IG E-Sign Agent (Windows)** workflow (manual dispatch) — builds both the `.exe` installer and the Store `.msix`. Add `MSIX_PACKAGE_NAME` and `MSIX_PUBLISHER` repository secrets first; see **[STORE.md](STORE.md)**.

## Microsoft Store (MSIX)

See **[STORE.md](STORE.md)** for the full Partner Center upload guide.

```powershell
copy build\windows\msix\store.config.example.json build\windows\msix\store.config.json
# Fill packageName + publisher from Partner Center → Product identity
powershell -ExecutionPolicy Bypass -File build\windows\build-msix.ps1
```

Output: `desktop-agent/releases/IG-E-Sign-Agent.msix`

Branding assets live in `desktop-agent/assets/` (`agent_icon.png`, `agent_icon.ico`, `ig-logo-light.png`). Regenerate icons from the portal logo with:

```bash
python desktop-agent/build_icons.py
```

The build script and PyInstaller spec run this automatically before packaging.

## Windows Defender / SmartScreen

The agent is a **PyInstaller** bundle and is **not code-signed yet**, so Windows Defender or SmartScreen may flag it as an unknown app. This is a common false positive for new internal tools.

**If blocked on download or install:**

1. In Windows Security → **Virus & threat protection** → **Protection history**, choose the IG E-Sign Agent item → **Allow** / **Restore**.
2. Or add an exclusion for the install folder, e.g. `%LOCALAPPDATA%\Programs\IG E-Sign Agent`.
3. Enterprise PCs: ask IT to allowlist `IG-E-Sign-Agent-Setup.exe` or the install path.

**For production:** sign the installer with an Authenticode certificate (EV recommended) so SmartScreen trust builds over time. Submit false positives at [Microsoft security intelligence](https://www.microsoft.com/en-us/wdsi/filesubmission).

Only download the agent from your IG E-Sign portal (`/dashboard/agent/download/`), not third-party links.

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

## Allowed browser origins (ERP integrations)

When signing is triggered from a web app (e.g. Microsoft Dynamics Business Central), the browser sends an `Origin` header. The agent allows:

- Your paired portal URL automatically
- Extra origins you add in the agent UI (**Allowed browser origins**) or via CLI:

```bash
python desktop-agent/agent.py origins list
python desktop-agent/agent.py origins add https://businesscentral.dynamics.com
python desktop-agent/agent.py origins remove https://businesscentral.dynamics.com
```

Origins must be full scheme + host only (`https://host`), no path. Changes apply immediately — no restart required.

## Token PIN memory

By default the agent remembers your USB token PIN after the first prompt so you are not asked on every signature. Configure this on **Token & PIN** in the agent window, or in `~/.ig-esign-agent/config.json`:

| Setting | Default | Description |
|--------|---------|-------------|
| `pin_cache_enabled` | `true` | Remember PIN between signatures |
| `pin_cache_hours` | `6` | Re-prompt after this many hours (`0` = until token removed) |
| `pin_clear_on_disconnect` | `true` | Clear saved PIN when the USB token is removed or changed |

Environment overrides (useful for IT deployment):

```bash
export IG_AGENT_PIN_CACHE_ENABLED=true
export IG_AGENT_PIN_CACHE_HOURS=6
export IG_AGENT_PIN_CLEAR_ON_DISCONNECT=true
```

Use **Clear saved PIN** in the agent UI to force a fresh prompt on the next signature. A wrong PIN also clears the cache automatically.

## Portal flow

1. **USB Sign** → upload PDF
2. Browser calls local agent on `127.0.0.1:9765`
3. Agent fetches job from `/api/agent/jobs/<id>/`, signs, completes
4. Download signed PDF from portal

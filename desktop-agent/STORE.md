# Microsoft Store MSIX packaging for IG E-Sign Agent

This guide builds the **`.msix`** package for Partner Center upload. The existing **`.exe`** installer remains for portal download.

## Prerequisites

| Requirement | Notes |
|-------------|--------|
| **Windows 10/11** | MSIX must be built on Windows (or use GitHub Actions below) |
| **Python 3.12+** | Same as agent build |
| **Windows SDK** | Provides `makeappx.exe` — install via [Windows SDK](https://developer.microsoft.com/windows/downloads/windows-sdk/) or Visual Studio |
| **Partner Center product identity** | Name + Publisher from your reserved Store app |

Optional: Inno Setup (only if you also want the `.exe` in the same run).

---

## Step 1 — Get package identity from Partner Center

1. Open [Partner Center](https://partner.microsoft.com/dashboard) → **Apps and games** → your app.
2. Go to **Product identity** (or **Product management** → **Product identity**).
3. Copy:
   - **Package/Identity/Name** (e.g. `InciteGravity.IGESignAgent`)
   - **Publisher** (e.g. `CN=12345678-1234-1234-1234-123456789012`)
   - **Package/Properties/PublisherDisplayName** (e.g. `INCITEGRAVITY PRIVATE LIMITED`) → `publisherDisplayName`

These must match `store.config.json` exactly (case and spacing).

---

## Step 2 — Create store config

On Windows, from the repo root:

```powershell
copy build\windows\msix\store.config.example.json build\windows\msix\store.config.json
```

Edit `build\windows\msix\store.config.json` and paste your **packageName** and **publisher**.

---

## Step 3 — Build the MSIX

```powershell
powershell -ExecutionPolicy Bypass -File build\windows\build-msix.ps1
```

This will:

1. Run PyInstaller if `dist\IG-E-Sign-Agent\` is missing (or use `-Rebuild` to force).
2. Stage the bundle with `portal.url` (`https://sign.incitegravity.com` by default).
3. Generate Store logo assets under `Assets\`.
4. Write `AppxManifest.xml` with `runFullTrust` for PKCS#11 / USB signing.
5. Pack **`desktop-agent\releases\IG-E-Sign-Agent.msix`**.

### Build installer + MSIX together

```powershell
powershell -ExecutionPolicy Bypass -File build\windows\build-agent.ps1 -BuildMsix
```

### Environment variables

| Variable | Purpose |
|----------|---------|
| `AGENT_API_BASE` | Portal URL in `portal.url` (default: `https://sign.incitegravity.com`) |
| `MSIX_PACKAGE_NAME` | Override `packageName` without editing JSON |
| `MSIX_PUBLISHER` | Override `publisher` without editing JSON |
| `MSIX_PUBLISHER_DISPLAY_NAME` | Must match Partner Center **PublisherDisplayName** exactly (e.g. `INCITEGRAVITY PRIVATE LIMITED`) |
| `MSIX_SIGN_PFX` | Optional — sign locally for install testing |
| `MSIX_SIGN_PASSWORD` | PFX password |

---

## Step 4 — Test locally (optional)

Partner Center re-signs packages on upload; local install usually needs signing or developer mode.

**Option A — Developer Mode (quick test)**

1. Windows Settings → **Privacy & security** → **For developers** → enable **Developer Mode**.
2. Double-click `IG-E-Sign-Agent.msix` or:

```powershell
Add-AppxPackage -Path desktop-agent\releases\IG-E-Sign-Agent.msix
```

Unsigned MSIX may fail outside Developer Mode.

**Option B — Sign with your cert**

```powershell
$env:MSIX_SIGN_PFX = "C:\path\to\cert.pfx"
$env:MSIX_SIGN_PASSWORD = "your-password"
powershell -ExecutionPolicy Bypass -File build\windows\build-msix.ps1
```

---

## Step 5 — Upload to Partner Center

1. Partner Center → your app → **Packages** → **Upload new package**.
2. Select `desktop-agent\releases\IG-E-Sign-Agent.msix`.
3. Wait for validation (identity + version).
4. Complete **Pricing and availability** → **Submit for certification**.

### Version bumps

MSIX requires **four-part** versions. `0.3.0` in `desktop-agent/VERSION` becomes `0.3.0.0`. Each Store upload must increase the version (e.g. `0.3.1.0`).

---

## EXE or MSI app — Package URL (your current Store product type)

Microsoft does **not** accept OneDrive or Google Drive links. Use the **public versioned HTTPS URL** on your portal:

```
https://sign.incitegravity.com/downloads/agent/0.3.0/IG-E-Sign-Agent-Setup.exe
```

Replace `0.3.0` with the value in `desktop-agent/VERSION` after each release.

### Partner Center → Packages

| Field | Value |
|-------|--------|
| **Package URL** | `https://sign.incitegravity.com/downloads/agent/<VERSION>/IG-E-Sign-Agent-Setup.exe` |
| **App type** | EXE |
| **Architecture** | x64 |
| **Installer parameters** | `/VERYSILENT /NORESTART` |
| **Language** | English (United States) |

### Deploy checklist

1. Build installer (GitHub Actions → **IG-E-Sign-Agent-Setup** artifact).
2. Copy to server: `desktop-agent/releases/IG-E-Sign-Agent-Setup.exe`  
   Or set `USB_AGENT_INSTALLER_PATH` to the file path.
3. Deploy Django with this code and restart the app.
4. Verify in a browser (no login): open the Package URL — download should start immediately.
5. **Code-sign** the installer before Store submission (required for EXE/MSI apps).

The URL is also returned by `GET /api/agent/version/` as `store_download_url` and shown on **USB Agent** in the portal for admins.

When you release a new version, bump `desktop-agent/VERSION`, deploy the new `.exe`, and submit a **new** Package URL with the new version segment in Partner Center.

---

## GitHub Actions (same workflow as the .exe)

The existing **Build IG E-Sign Agent (Windows)** workflow now produces **both** artifacts:

| Artifact | File |
|----------|------|
| `IG-E-Sign-Agent-Setup` | `IG-E-Sign-Agent-Setup.exe` (portal download) |
| `IG-E-Sign-Agent-MSIX` | `IG-E-Sign-Agent.msix` (Partner Center upload) |

### One-time setup

Add two repository secrets (**Settings → Secrets and variables → Actions**):

| Secret | Value |
|--------|--------|
| `MSIX_PACKAGE_NAME` | Partner Center → **Product identity** → Package/Identity/Name |
| `MSIX_PUBLISHER` | Partner Center → **Product identity** → Publisher (`CN=...`) |

### Run the build

1. GitHub → **Actions** → **Build IG E-Sign Agent (Windows)** → **Run workflow**
2. When it finishes, download both artifacts from the run summary
3. Upload `IG-E-Sign-Agent.msix` to Partner Center → **Packages**

No extra checkbox — every workflow run builds the installer and the Store package.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `store.config.json not found` | Copy from `store.config.example.json` |
| `makeappx.exe not found` | Install Windows SDK |
| Identity mismatch on upload | Match Partner Center **Product identity** exactly |
| App won't install locally | Enable Developer Mode or sign with PFX |
| Certification fails on launch | Test MSIX on clean VM; verify pairing without USB token |

---

## Files

| Path | Purpose |
|------|---------|
| `build/windows/build-msix.ps1` | Main MSIX build script |
| `build/windows/msix/AppxManifest.xml.template` | Store manifest template |
| `build/windows/msix/store.config.json` | Your identity (create from example; not committed) |
| `build/windows/msix/build_store_assets.py` | Store logo PNGs |
| `desktop-agent/releases/IG-E-Sign-Agent.msix` | Upload this to Partner Center |

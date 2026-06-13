# Build IG E-Sign USB Agent for Windows (PyInstaller + Inno Setup)
# Run on Windows: powershell -ExecutionPolicy Bypass -File build\windows\build-agent.ps1

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$AgentVersion = (Get-Content (Join-Path $Root "desktop-agent\VERSION") -Raw).Trim()

Set-Location $Root

Write-Host "IG E-Sign Agent build v$AgentVersion"
Write-Host "Installing dependencies..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller

Write-Host "Building IG-E-Sign-Agent.exe..."
pyinstaller --noconfirm --clean (Join-Path $PSScriptRoot "IG-E-Sign-Agent.spec")

$Inno = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

$ReleaseDir = Join-Path $Root "desktop-agent\releases"
New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null

if (-not $Inno) {
    Write-Warning "Inno Setup not found. Bundle is at dist\IG-E-Sign-Agent\"
    Write-Warning "Install Inno Setup 6 from https://jrsoftware.org/isinfo.php"
    exit 0
}

$ApiBase = $env:AGENT_API_BASE
if (-not $ApiBase) {
    $ApiBase = "https://sign.incitegravity.com"
}
$PortalUrlPath = Join-Path $PSScriptRoot "agent-scripts\portal.url"
Set-Content -Path $PortalUrlPath -Value "api_base=$ApiBase" -Encoding ascii -NoNewline
Add-Content -Path $PortalUrlPath -Value "" -Encoding ascii
Write-Host "Portal URL: $ApiBase"

Write-Host "Building installer..."
Set-Location $PSScriptRoot
& $Inno "/DAgentVersion=$AgentVersion" "agent_installer.iss"

$InstallerSrc = Join-Path $PSScriptRoot "installer-output\IG-E-Sign-Agent-Setup.exe"
$InstallerDst = Join-Path $ReleaseDir "IG-E-Sign-Agent-Setup.exe"
Copy-Item -Force $InstallerSrc $InstallerDst

Write-Host "Done."
Write-Host "Installer: $InstallerDst"
Write-Host "Set USB_AGENT_INSTALLER_PATH=$InstallerDst on the server for portal download."

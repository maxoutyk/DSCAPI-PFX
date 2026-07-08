# Build IG E-Sign USB Agent for Windows (PyInstaller + optional Microsoft Store MSIX)
# Run on Windows: powershell -ExecutionPolicy Bypass -File build\windows\build-agent.ps1
# Optional: -BuildMsix produces desktop-agent\releases\IG-E-Sign-Agent.msix for Partner Center

param(
    [switch]$BuildMsix
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$AgentVersion = (Get-Content (Join-Path $Root "desktop-agent\VERSION") -Raw).Trim()

Set-Location $Root

Write-Host "IG E-Sign Agent build v$AgentVersion"
Write-Host "Regenerating branding icons..."
python (Join-Path $Root "desktop-agent\build_icons.py")

Write-Host "Installing dependencies..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller

Write-Host "Building IG-E-Sign-Agent.exe..."
pyinstaller --noconfirm --clean (Join-Path $PSScriptRoot "IG-E-Sign-Agent.spec")

$DistDir = Join-Path $Root "dist\IG-E-Sign-Agent"
Copy-Item -Force (Join-Path $Root "desktop-agent\assets\agent_icon.ico") (Join-Path $DistDir "agent_icon.ico")

$ReleaseDir = Join-Path $Root "desktop-agent\releases"
New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null
Copy-Item -Force (Join-Path $Root "desktop-agent\assets\agent_icon.ico") (Join-Path $ReleaseDir "agent_icon.ico")

Write-Host "Done."
Write-Host "PyInstaller bundle: $DistDir"
Write-Host "Users install via the Microsoft Store listing (see desktop-agent/STORE.md)."

if ($BuildMsix) {
    Write-Host ""
    Write-Host "Building Microsoft Store MSIX package..."
    & (Join-Path $PSScriptRoot "build-msix.ps1") -SkipSign
}

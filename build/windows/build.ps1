# Build DSCAPI-PFX Windows app + installer (run on Windows with PowerShell)
# Requires: Python 3.12, Inno Setup 6 (https://jrsoftware.org/isinfo.php)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")

Set-Location $Root

Write-Host "Installing dependencies..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller

Write-Host "Building executable..."
pyinstaller --noconfirm --clean (Join-Path $PSScriptRoot "DSCAPI-PFX.spec")

$Inno = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $Inno) {
    Write-Warning "Inno Setup not found. Executable is at dist\DSCAPI-PFX\"
    Write-Warning "Install Inno Setup 6 and re-run this script to create DSCAPI-PFX-Setup.exe"
    exit 0
}

Write-Host "Building installer with Inno Setup..."
Set-Location (Join-Path $PSScriptRoot)
& $Inno "installer.iss"

Write-Host "Done."
Write-Host "Installer: build\windows\installer-output\DSCAPI-PFX-Setup.exe"

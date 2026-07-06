# Build IG E-Sign Agent MSIX package for Microsoft Store upload.
# Run on Windows (after PyInstaller bundle exists, or pass -Rebuild).
#
#   powershell -ExecutionPolicy Bypass -File build\windows\build-msix.ps1
#
# First-time setup:
#   1. Partner Center → your app → Product identity → copy Name and Publisher
#   2. Copy build\windows\msix\store.config.example.json → store.config.json
#   3. Fill packageName and publisher in store.config.json
#
# Optional env:
#   AGENT_API_BASE          Portal URL baked into portal.url (default: https://sign.incitegravity.com)
#   MSIX_PACKAGE_NAME       Override package identity name
#   MSIX_PUBLISHER          Override publisher DN
#   MSIX_SIGN_PFX           Path to .pfx for local test signing (optional)
#   MSIX_SIGN_PASSWORD      PFX password (optional)

param(
    [switch]$Rebuild,
    [switch]$SkipSign
)

$ErrorActionPreference = 'Stop'
$Root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$MsixDir = Join-Path $PSScriptRoot 'msix'
$DistDir = Join-Path $Root 'dist\IG-E-Sign-Agent'
$ReleaseDir = Join-Path $Root 'desktop-agent\releases'
$StagingDir = Join-Path $PSScriptRoot 'msix-staging'
$VersionFile = Join-Path $Root 'desktop-agent\VERSION'
$AgentVersion = (Get-Content $VersionFile -Raw).Trim()

function ConvertTo-MsixVersion([string]$Version) {
    $parts = @()
    foreach ($piece in ($Version -split '\.')) {
        $digits = -join (($piece.ToCharArray() | Where-Object { $_ -match '\d' }))
        if (-not $digits) { $digits = '0' }
        $parts += [int]$digits
    }
    while ($parts.Count -lt 4) { $parts += 0 }
    return ($parts[0..3] -join '.')
}

function Read-StoreConfig {
    $configPath = Join-Path $MsixDir 'store.config.json'
    if (Test-Path $configPath) {
        $config = Get-Content $configPath -Raw | ConvertFrom-Json
    } elseif ($env:MSIX_PACKAGE_NAME -and $env:MSIX_PUBLISHER) {
        Write-Host 'Using MSIX identity from environment variables.'
        $config = [pscustomobject]@{
            packageName = $env:MSIX_PACKAGE_NAME
            publisher = $env:MSIX_PUBLISHER
            publisherDisplayName = if ($env:MSIX_PUBLISHER_DISPLAY_NAME) { $env:MSIX_PUBLISHER_DISPLAY_NAME } else { 'Incite Gravity' }
            displayName = if ($env:MSIX_DISPLAY_NAME) { $env:MSIX_DISPLAY_NAME } else { 'IG E-Sign Agent' }
            description = if ($env:MSIX_DESCRIPTION) {
                $env:MSIX_DESCRIPTION
            } else {
                'Class 3 USB DSC signing companion for IG E-Sign by Incite Gravity'
            }
        }
    } else {
        throw @"
store.config.json not found.

Copy the example and fill Partner Center product identity values:
  copy build\windows\msix\store.config.example.json build\windows\msix\store.config.json

Partner Center → Apps and games → [your app] → Product identity
  - Package/Identity/Name  → packageName
  - Publisher              → publisher (starts with CN=)

Or set environment variables MSIX_PACKAGE_NAME and MSIX_PUBLISHER.
"@
    }
    if ($env:MSIX_PACKAGE_NAME) { $config.packageName = $env:MSIX_PACKAGE_NAME }
    if ($env:MSIX_PUBLISHER) { $config.publisher = $env:MSIX_PUBLISHER }
    foreach ($key in @('packageName', 'publisher', 'publisherDisplayName', 'displayName', 'description')) {
        if (-not $config.$key) {
            throw "store.config.json is missing required field: $key"
        }
        if ($config.$key -match 'REPLACE_WITH|XXXXXXXX') {
            throw "store.config.json still contains placeholder values for $key. Fill values from Partner Center product identity."
        }
    }
    return $config
}

function Find-WindowsSdkTool([string]$ToolName) {
    $kitsRoot = @(
        "${env:ProgramFiles(x86)}\Windows Kits\10\bin",
        "${env:ProgramFiles}\Windows Kits\10\bin"
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $kitsRoot) {
        throw 'Windows 10/11 SDK not found. Install "Windows SDK" from Visual Studio Installer or https://developer.microsoft.com/windows/downloads/windows-sdk/'
    }
    $versionDir = Get-ChildItem $kitsRoot -Directory | Sort-Object Name -Descending | Select-Object -First 1
    $toolPath = Join-Path $versionDir.FullName "x64\$ToolName"
    if (-not (Test-Path $toolPath)) {
        throw "$ToolName not found under $($versionDir.FullName)\x64"
    }
    return $toolPath
}

function Write-PortalUrl([string]$Path, [string]$ApiBase) {
    Set-Content -Path $Path -Value "api_base=$ApiBase" -Encoding ascii -NoNewline
    Add-Content -Path $Path -Value '' -Encoding ascii
}

function Render-ManifestTemplate {
    param(
        [string]$TemplatePath,
        [string]$OutputPath,
        [hashtable]$Tokens
    )
    $xml = Get-Content $TemplatePath -Raw
    foreach ($key in $Tokens.Keys) {
        $xml = $xml.Replace("{{$key}}", [System.Security.SecurityElement]::Escape($Tokens[$key]))
    }
  # SecurityElement.Escape over-escapes quotes; restore publisher DN quotes if needed
    $xml = $xml.Replace('&quot;', '"')
    Set-Content -Path $OutputPath -Value $xml -Encoding utf8
}

$PackageVersion = ConvertTo-MsixVersion $AgentVersion
Write-Host "IG E-Sign Agent MSIX build v$AgentVersion ($PackageVersion)"

if ($Rebuild -or -not (Test-Path (Join-Path $DistDir 'IG-E-Sign-Agent.exe'))) {
    Write-Host 'PyInstaller bundle missing or -Rebuild set — running build-agent.ps1 (installer optional)...'
    & (Join-Path $PSScriptRoot 'build-agent.ps1')
}

if (-not (Test-Path (Join-Path $DistDir 'IG-E-Sign-Agent.exe'))) {
    throw "PyInstaller output not found: $DistDir\IG-E-Sign-Agent.exe"
}

$config = Read-StoreConfig
$ApiBase = $env:AGENT_API_BASE
if (-not $ApiBase) { $ApiBase = 'https://sign.incitegravity.com' }

Write-Host "Package identity: $($config.packageName)"
Write-Host "Publisher: $($config.publisher)"
Write-Host "Portal URL: $ApiBase"

if (Test-Path $StagingDir) { Remove-Item $StagingDir -Recurse -Force }
New-Item -ItemType Directory -Force -Path $StagingDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $StagingDir 'Assets') | Out-Null

Write-Host 'Staging PyInstaller bundle...'
Copy-Item -Path (Join-Path $DistDir '*') -Destination $StagingDir -Recurse -Force
Write-PortalUrl -Path (Join-Path $StagingDir 'portal.url') -ApiBase $ApiBase

Write-Host 'Generating Store logo assets...'
python (Join-Path $MsixDir 'build_store_assets.py') `
    --icon (Join-Path $Root 'desktop-agent\assets\agent_icon.png') `
    --out (Join-Path $StagingDir 'Assets')

$manifestPath = Join-Path $StagingDir 'AppxManifest.xml'
Render-ManifestTemplate `
    -TemplatePath (Join-Path $MsixDir 'AppxManifest.xml.template') `
    -OutputPath $manifestPath `
    -Tokens @{
        PACKAGE_NAME = [string]$config.packageName
        PUBLISHER = [string]$config.publisher
        PACKAGE_VERSION = $PackageVersion
        DISPLAY_NAME = [string]$config.displayName
        PUBLISHER_DISPLAY_NAME = [string]$config.publisherDisplayName
        DESCRIPTION = [string]$config.description
    }

New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null
$MsixOutput = Join-Path $ReleaseDir 'IG-E-Sign-Agent.msix'
if (Test-Path $MsixOutput) { Remove-Item $MsixOutput -Force }

$makeAppx = Find-WindowsSdkTool 'makeappx.exe'
Write-Host "Packing MSIX with $makeAppx ..."
& $makeAppx pack /d $StagingDir /p $MsixOutput /o
if ($LASTEXITCODE -ne 0) { throw "makeappx pack failed with exit code $LASTEXITCODE" }

if (-not $SkipSign -and $env:MSIX_SIGN_PFX -and (Test-Path $env:MSIX_SIGN_PFX)) {
    $signtool = Find-WindowsSdkTool 'signtool.exe'
    $pfxPassword = if ($env:MSIX_SIGN_PASSWORD) { $env:MSIX_SIGN_PASSWORD } else { '' }
    $signArgs = @(
        'sign', '/fd', 'SHA256',
        '/f', $env:MSIX_SIGN_PFX,
        '/p', $pfxPassword,
        $MsixOutput
    )
    Write-Host 'Signing MSIX for local testing...'
    & $signtool @signArgs
    if ($LASTEXITCODE -ne 0) { throw "signtool sign failed with exit code $LASTEXITCODE" }
} else {
    Write-Host 'Skipping local signing (Partner Center will sign on upload).'
    Write-Host 'For local install tests, set MSIX_SIGN_PFX or pass -SkipSign explicitly.'
}

Write-Host ''
Write-Host 'Done.'
Write-Host "MSIX package: $MsixOutput"
Write-Host ''
Write-Host 'Next steps:'
Write-Host '  1. Partner Center → your app → Packages → Upload new package'
Write-Host '  2. Select IG-E-Sign-Agent.msix'
Write-Host '  3. Complete submission and submit for certification'

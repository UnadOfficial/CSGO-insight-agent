#Requires -Version 5.1
<#
.SYNOPSIS
  One-click Windows NSIS package for CS2 Insight Agent (Tauri desktop:build:ver).

.DESCRIPTION
  Fast path (default): verify the backend venv / lean parser, then build the
  installer for -Version.

  Full path (-Full): rebuild the patched demoparser2 wheel from source, force
  refresh the repo-root python\ runtime, then build.

.PARAMETER Version
  Semver used for the frontend, Tauri/NSIS metadata, and embedded backend
  (same as `pnpm run desktop:build:ver -- <version>`).

.PARAMETER Full
  First-time / reproducible build: setup-backend-dev.ps1 -BuildFromSource,
  CS2_INSIGHT_DEMOPARSER_WHEEL + CS2_INSIGHT_REFRESH_PYTHON=1, pnpm install.

.PARAMETER SkipPnpmInstall
  Skip `pnpm install --frozen-lockfile` (still runs on -Full unless set).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\packaging\windows\build_desktop.ps1 -Version 2.6.0

.EXAMPLE
  .\packaging\windows\build_desktop.ps1 -Version 2.6.0 -Full
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$')]
    [string]$Version,

    [switch]$Full,

    [switch]$SkipPnpmInstall
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$frontend = Join-Path $repoRoot "frontend"
$setupBackend = Join-Path $repoRoot "packaging\demoparser-lean\setup-backend-dev.ps1"
$runtimeMeta = Join-Path $repoRoot "packaging\demoparser-lean\demoparser-runtime.json"
$wheelsDir = Join-Path $repoRoot "dist\wheels"

function Invoke-Checked {
    param(
        [Parameter(Mandatory)][string]$Label,
        [Parameter(Mandatory)][scriptblock]$Action
    )
    Write-Host "==> $Label"
    & $Action
    if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) {
        throw "$Label failed (exit $LASTEXITCODE)."
    }
}

if (-not (Test-Path -LiteralPath $setupBackend)) {
    throw "Missing $setupBackend"
}
if (-not (Test-Path -LiteralPath $frontend)) {
    throw "Missing frontend directory: $frontend"
}

Push-Location $repoRoot
$wheelEnvSet = $false
$refreshEnvSet = $false
try {
    if ($Full) {
        Invoke-Checked "Backend venv + patched demoparser2 wheel (from source)" {
            & $setupBackend -BuildFromSource
        }

        $runtime = Get-Content -LiteralPath $runtimeMeta -Raw | ConvertFrom-Json
        $filter = "demoparser2-$($runtime.distribution_version)-cp312-cp312-win_amd64.whl"
        $wheel = Get-ChildItem -LiteralPath $wheelsDir -File -Filter $filter -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTimeUtc -Descending |
            Select-Object -First 1
        if (-not $wheel) {
            throw "Required wheel not found: $wheelsDir\$filter"
        }

        $env:CS2_INSIGHT_DEMOPARSER_WHEEL = $wheel.FullName
        $env:CS2_INSIGHT_REFRESH_PYTHON = "1"
        $wheelEnvSet = $true
        $refreshEnvSet = $true
        Write-Host "Using demoparser wheel: $($wheel.FullName)"
    } else {
        Invoke-Checked "Verify backend venv / lean parser" {
            & $setupBackend
        }
    }

    Push-Location $frontend
    try {
        if ($Full -and -not $SkipPnpmInstall) {
            Invoke-Checked "pnpm install --frozen-lockfile" {
                & pnpm.cmd install --frozen-lockfile
            }
        } elseif (-not $SkipPnpmInstall -and -not (Test-Path -LiteralPath (Join-Path $frontend "node_modules"))) {
            Invoke-Checked "pnpm install --frozen-lockfile (node_modules missing)" {
                & pnpm.cmd install --frozen-lockfile
            }
        }

        Invoke-Checked "desktop:build:ver $Version" {
            & pnpm.cmd run desktop:build:ver -- $Version
        }
    } finally {
        Pop-Location
    }

    $installer = Join-Path $frontend "src-tauri\target\release\bundle\nsis\CS2 Insight Agent_${Version}_x64-setup.exe"
    $sig = "$installer.sig"
    Write-Host ""
    Write-Host "Build finished."
    if (Test-Path -LiteralPath $installer) {
        Write-Host "Installer: $installer"
    } else {
        Write-Host "Expected installer (if NSIS succeeded): $installer"
    }
    if (Test-Path -LiteralPath $sig) {
        Write-Host "Updater sig: $sig"
    } else {
        Write-Host "No .sig (updater private key not used)."
    }
} finally {
    if ($wheelEnvSet) {
        Remove-Item Env:CS2_INSIGHT_DEMOPARSER_WHEEL -ErrorAction SilentlyContinue
    }
    if ($refreshEnvSet) {
        Remove-Item Env:CS2_INSIGHT_REFRESH_PYTHON -ErrorAction SilentlyContinue
    }
    Pop-Location
}

#Requires -Version 5.1
<#
.SYNOPSIS
  One-click Tauri desktop:dev. Does not build an NSIS installer.

.DESCRIPTION
  Starts the daily desktop loop from the repository root:
  Vite HMR for React/CSS, debug Tauri shell, Python backend from .venv.

  Missing .venv or frontend node_modules are created automatically.
  Use -Setup to force uv sync + pnpm install even when they already exist.

.PARAMETER Setup
  Always refresh the backend venv and frontend dependencies before start.

.PARAMETER Browser
  Start uvicorn + Vite only (http://localhost:5173). No Tauri window.

.EXAMPLE
  .\packaging\windows\dev_desktop.ps1
  .\dev.bat
  .\dev.bat -Browser
#>
[CmdletBinding()]
param(
    [switch]$Setup,
    [switch]$Browser
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

try {
    if ($env:ComSpec) { & $env:ComSpec /c "chcp 65001>nul" | Out-Null }
    $utf8 = [System.Text.UTF8Encoding]::new($false)
    [Console]::OutputEncoding = $utf8
    [Console]::InputEncoding = $utf8
    $OutputEncoding = $utf8
} catch { }

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$frontend = Join-Path $repoRoot "frontend"
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$setupBackend = Join-Path $repoRoot "packaging\demoparser-lean\setup-backend-dev.ps1"
$tauriCmd = Join-Path $frontend "node_modules\.bin\tauri.cmd"

function Write-Step {
    param([string]$Message)
    Write-Host "==> $Message"
}

function Assert-Command {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$Hint
    )
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name 未找到。$Hint"
    }
}

function Get-PnpmCmd {
    $cmd = Get-Command pnpm.cmd -ErrorAction SilentlyContinue
    if (-not $cmd) { $cmd = Get-Command pnpm -ErrorAction SilentlyContinue }
    if (-not $cmd) {
        throw "pnpm 未找到。请安装 Node.js 22 和 pnpm 11.9.0 后重试。"
    }
    return $cmd.Source
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory)][string]$Label,
        [Parameter(Mandatory)][scriptblock]$Action
    )
    Write-Step $Label
    & $Action
    if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) {
        throw "$Label 失败（退出码 $LASTEXITCODE）。"
    }
}

if (-not (Test-Path -LiteralPath $frontend -PathType Container)) {
    throw "未找到 frontend 目录：$frontend"
}
if (-not (Test-Path -LiteralPath $setupBackend -PathType Leaf)) {
    throw "未找到后端配置脚本：$setupBackend"
}

Set-Location -LiteralPath $repoRoot
try {
    if ($Host.UI -and $Host.UI.RawUI) {
        $Host.UI.RawUI.WindowTitle = "CSGO Insight Agent - 开发"
    }
} catch { }

$needBackend = $Setup -or -not (Test-Path -LiteralPath $python -PathType Leaf)
$needFrontend = $Setup -or -not (Test-Path -LiteralPath $tauriCmd -PathType Leaf)

if ($needBackend) {
    Assert-Command "uv" "请先安装 uv 0.11.x。"
    Invoke-Checked "同步后端 .venv（uv sync，不打包）" {
        & $setupBackend
    }
}

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "后端 Python 仍不可用：$python"
}

if ($needFrontend) {
    $pnpm = Get-PnpmCmd
    Invoke-Checked "安装前端依赖（pnpm install --frozen-lockfile）" {
        & $pnpm --dir $frontend install --frozen-lockfile
    }
}

if ($Browser) {
    Write-Host ""
    Write-Host "CSGO Insight Agent - 浏览器开发（不打包、不启动 Tauri）"
    Write-Host "  后端  http://127.0.0.1:8000"
    Write-Host "  前端  http://localhost:5173  （/api 代理到后端）"
    Write-Host "关闭本窗口会停止两个进程。"
    Write-Host ""

    $pnpm = Get-PnpmCmd
    $backend = Start-Process -FilePath $python -ArgumentList @(
        "-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--reload", "--port", "8000"
    ) -WorkingDirectory $repoRoot -PassThru -NoNewWindow
    $frontendProc = $null
    try {
        $frontendProc = Start-Process -FilePath $pnpm -ArgumentList @("run", "dev") `
            -WorkingDirectory $frontend -PassThru -NoNewWindow
        $deadline = (Get-Date).AddSeconds(45)
        while ((Get-Date) -lt $deadline) {
            Start-Sleep -Milliseconds 400
            try {
                Invoke-WebRequest -Uri "http://localhost:5173" -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop | Out-Null
                Start-Process "http://localhost:5173"
                break
            } catch { }
        }
        Wait-Process -Id $frontendProc.Id
    } finally {
        foreach ($proc in @($frontendProc, $backend)) {
            if ($null -eq $proc) { continue }
            try {
                if (-not $proc.HasExited) {
                    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
                }
            } catch { }
        }
    }
    exit 0
}

Assert-Command "cargo" "Tauri 开发需要 Rust stable（MSVC）和 Visual Studio C++ 生成工具。"
if (-not (Test-Path -LiteralPath $tauriCmd -PathType Leaf)) {
    throw "前端依赖未安装完整，缺少 $tauriCmd"
}

Write-Host ""
Write-Host "CSGO Insight Agent - Tauri 热更新开发"
Write-Host "  前端改动走 Vite HMR，不会生成 NSIS 安装包。"
Write-Host "  后端由 Tauri 从仓库 .venv 自动拉起。"
Write-Host "  日常改代码请用本脚本；只有验证安装/发布时才运行 build_desktop。"
Write-Host ""

$pnpm = Get-PnpmCmd
Set-Location -LiteralPath $frontend
& $pnpm run desktop:dev
exit $LASTEXITCODE

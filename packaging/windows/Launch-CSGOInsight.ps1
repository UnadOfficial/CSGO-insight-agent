#Requires -Version 5.1
# Launches the bundled backend; opens default browser once the web UI responds.
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
try {
  if ($env:ComSpec) { & $env:ComSpec /c "chcp 65001>nul" | Out-Null }
} catch { }
$cs2Utf8 = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $cs2Utf8
[Console]::InputEncoding = $cs2Utf8
$OutputEncoding = $cs2Utf8

$appRoot = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
if (-not $appRoot) {
  Write-Host "[CSGO Insight Agent] Cannot resolve install directory." -ForegroundColor Red
  Read-Host "Press Enter to exit"
  exit 1
}
Set-Location -LiteralPath $appRoot
try {
  if ($Host.UI -and $Host.UI.RawUI) {
    $Host.UI.RawUI.WindowTitle = "CSGO Insight Agent"
  }
} catch {
}
$py = Join-Path $appRoot "python\python.exe"
$wd = Join-Path $appRoot "backend"

$hostOnly = "127.0.0.1"
if ($env:CSGO_INSIGHT_HOST) {
  $t = $env:CSGO_INSIGHT_HOST.Trim()
  if ($t) { $hostOnly = $t }
}
$port = 19871
if ($env:CSGO_INSIGHT_PORT) {
  $parsed = 0
  if ([int]::TryParse($env:CSGO_INSIGHT_PORT, [ref]$parsed) -and $parsed -ge 1 -and $parsed -le 65535) {
    $port = $parsed
  }
}

# Single source of truth: publish the resolved port so the uvicorn listener and the
# GSI sink URL written into gamestate_integration_*.cfg cannot diverge. Without this
# the backend listened on 19871 while the GSI sink defaulted to 8000, so CS:GO posted
# its state to a dead port and recording aborted with "CS:GO 未在限定时间内进入游戏画面".
$env:CSGO_INSIGHT_PORT = "$port"

$openUrl = "http://$($hostOnly):$port/"

if (-not (Test-Path -LiteralPath $py)) {
  Write-Host "[CSGO Insight Agent] python.exe not found: $py" -ForegroundColor Red
  Read-Host "Press Enter to exit"
  exit 1
}

$browserJob = $null
try {
  $browserJob = Start-Job -ScriptBlock {
    param($Url)
    $ProgressPreference = "SilentlyContinue"
    $deadline = (Get-Date).AddSeconds(90)
    while ((Get-Date) -lt $deadline) {
      Start-Sleep -Milliseconds 400
      try {
        Invoke-WebRequest -Uri $Url -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop | Out-Null
        Start-Process $Url
        break
      } catch {
      }
    }
  } -ArgumentList $openUrl
} catch {
  Write-Warning "[CSGO Insight Agent] Could not start browser waiter job: $($_.Exception.Message). Open $openUrl manually when the server is ready."
}

$pushed = $false
try {
  if (-not (Test-Path -LiteralPath $wd)) {
    throw "Backend folder not found: $wd"
  }
  Push-Location $wd
  $pushed = $true
  & $py -m app.run_server
  if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) {
    throw "python exited with code $LASTEXITCODE"
  }
} catch {
  Write-Host "[CSGO Insight Agent] $($_.Exception.Message)" -ForegroundColor Red
  if ($_.ScriptStackTrace) { Write-Host $_.ScriptStackTrace -ForegroundColor DarkRed }
  Read-Host "Press Enter to exit"
  exit 1
} finally {
  if ($pushed) {
    Pop-Location
  }
  Get-Job -ErrorAction SilentlyContinue | Stop-Job -ErrorAction SilentlyContinue
  Get-Job -ErrorAction SilentlyContinue | Remove-Job -Force -ErrorAction SilentlyContinue
}

# start_app.ps1 - Starts Mega Ticket Lab and opens it in your browser.
#
# Run from the project root (or double-click via a shortcut):
#   powershell -ExecutionPolicy Bypass -File .\start_app.ps1           # dev mode: .venv Python + run.py
#   powershell -ExecutionPolicy Bypass -File .\start_app.ps1 -Exe      # run dist\MegaTicketLab.exe instead
# Options:
#   -Exe         start the built exe (dist\MegaTicketLab.exe) instead of run.py
#   -NoBrowser   don't open the browser
#   -Restart     stop a copy that is already running on the port, then start fresh
#
# Press Ctrl+C in this window to stop the app (dev mode). In -Exe mode the
# exe runs in its own window - close that window to stop it.

param(
    [switch]$Exe,
    [switch]$NoBrowser,
    [switch]$Restart
)

# "Continue" on purpose: Flask writes its request log to stderr, which
# Windows PowerShell 5.1 would otherwise treat as an error and stop on.
$ErrorActionPreference = "Continue"
Set-Location -Path $PSScriptRoot

function Info($text) { Write-Host $text -ForegroundColor Cyan }
function Ok($text)   { Write-Host $text -ForegroundColor Green }
function Warn($text) { Write-Host $text -ForegroundColor Yellow }
function Fail($text) { Write-Host "ERROR: $text" -ForegroundColor Red; exit 1 }

# ---------------------------------------------------------- host / port from config.ini
$appHost = "127.0.0.1"; $port = "5000"; $game = "mega_millions"
if (Test-Path "config.ini") {
    $section = ""
    foreach ($line in Get-Content "config.ini") {
        $l = ($line -replace "[;#].*$", "").Trim()
        if ($l -match "^\[(.+)\]$") { $section = $Matches[1].Trim().ToLower(); continue }
        if ($l -match "^([^=]+)=(.*)$") {
            $key = $Matches[1].Trim().ToLower(); $val = $Matches[2].Trim()
            if ($section -eq "app" -and $key -eq "host") { $appHost = $val }
            if ($section -eq "app" -and $key -eq "port") { $port = $val }
            if ($section -eq "game" -and $key -eq "name") { $game = $val }
        }
    }
}
$browserHost = if ($appHost -eq "0.0.0.0") { "127.0.0.1" } else { $appHost }
$url = "http://$($browserHost):$port"

function Test-AppUp {
    try { Invoke-RestMethod -Uri "$url/api/game" -TimeoutSec 2 } catch { $null }
}

function Wait-AppUp($seconds) {
    for ($i = 0; $i -lt ($seconds * 2); $i++) {
        $info = Test-AppUp
        if ($info) { return $info }
        Start-Sleep -Milliseconds 500
    }
    return $null
}

Write-Host "==============================================" -ForegroundColor Cyan
Write-Host "  Mega Ticket Lab - $game" -ForegroundColor Cyan
Write-Host "  $url" -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan

# ---------------------------------------------------------- already running?
$listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    $owner = Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue
    if ($Restart) {
        Warn "Stopping the copy already running on port $port ($($owner.ProcessName), PID $($listener.OwningProcess))..."
        Stop-Process -Id $listener.OwningProcess -Force -ErrorAction SilentlyContinue
        Get-Process -Name "MegaTicketLab" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    } elseif (Test-AppUp) {
        Ok "Mega Ticket Lab is already running on $url."
        if (-not $NoBrowser) { Start-Process $url }
        Write-Host "Use -Restart to stop it and start a fresh copy."
        exit 0
    } else {
        Fail "Port $port is used by another program ($($owner.ProcessName), PID $($listener.OwningProcess)). Close it, use -Restart, or change [app] port in config.ini."
    }
}

# ---------------------------------------------------------- exe mode
if ($Exe) {
    $exePath = Join-Path $PSScriptRoot "dist\MegaTicketLab.exe"
    if (-not (Test-Path $exePath)) { Fail "dist\MegaTicketLab.exe not found. Run .\full_rebuild.ps1 first." }
    Info "Starting $exePath ..."
    Start-Process -FilePath $exePath -WorkingDirectory (Split-Path $exePath)
    $info = Wait-AppUp 30
    if (-not $info) { Fail "The exe did not answer on $url within 30 seconds. Check its window for errors." }
    Ok "Running: $($info.title) - $($info.draws_loaded) draw(s) loaded (source: $($info.source))."
    if ($info.source -ne "workbook") { Warn "Using fallback data: $($info.reason)" }
    if (-not $NoBrowser) { Start-Process $url }
    Write-Host "The app runs in its own window - close that window to stop it."
    exit 0
}

# ---------------------------------------------------------- dev mode (run.py)
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { Fail ".venv not found. Run .\full_rebuild.ps1 (or .\rebuild.ps1) first." }

# Open the browser once the server answers, without blocking the server.
if (-not $NoBrowser) {
    Start-Job -ArgumentList $url -ScriptBlock {
        param($u)
        for ($i = 0; $i -lt 60; $i++) {
            try { Invoke-RestMethod -Uri "$u/api/game" -TimeoutSec 2 | Out-Null; Start-Process $u; return } catch { }
            Start-Sleep -Milliseconds 500
        }
    } | Out-Null
}

Info "Starting the app with $py run.py"
Info "Press Ctrl+C to stop.`n"
& $py run.py
$code = $LASTEXITCODE

Get-Job | Remove-Job -Force -ErrorAction SilentlyContinue
if ($code -and $code -ne 0) { Fail "The app stopped with exit code $code (see the messages above)." }
Ok "`nApp stopped."

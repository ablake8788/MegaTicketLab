# full_rebuild.ps1 - Full clean rebuild of Mega Ticket Lab.
#
#   1. Stops any running MegaTicketLab.exe
#   2. Deletes .venv, build, dist, caches and the old .spec
#   3. Creates a fresh virtual environment and installs requirements + PyInstaller
#   4. Runs the test suite (stops if anything fails)
#   5. Checks the data file named in config.ini
#   6. Builds dist\MegaTicketLab.exe
#   7. Smoke-tests the exe (starts it, calls /api/game, stops it)
#
# Run from the project root:
#   powershell -ExecutionPolicy Bypass -File .\full_rebuild.ps1
# Options:
#   -SkipTests      skip step 4
#   -SkipSmokeTest  skip step 7
#   -Launch         start the app (python run.py) when the build is done

param(
    [switch]$SkipTests,
    [switch]$SkipSmokeTest,
    [switch]$Launch
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
$started = Get-Date

function Step($text) { Write-Host "`n== $text" -ForegroundColor Cyan }
function Ok($text)   { Write-Host "   $text" -ForegroundColor Green }
function Warn($text) { Write-Host "   WARNING: $text" -ForegroundColor Yellow }
function Fail($text) { Write-Host "`nFAILED: $text" -ForegroundColor Red; exit 1 }

# Runs a native command (python, pip, PyInstaller) and fails only on a non-zero exit code.
# PyInstaller and pip write normal progress to stderr; Windows PowerShell 5.1 turns
# stderr lines into errors under "Stop", so stderr is relaxed and printed as plain text here.
function Run($exe, [string[]]$argList, $what) {
    $oldPref = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $exe @argList 2>&1 | ForEach-Object { Write-Host "$_" }
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $oldPref
    }
    if ($code -ne 0) { Fail "$what (exit code $code)" }
}

function Read-Ini($path) {
    $ini = @{}; $section = ""
    foreach ($line in Get-Content $path) {
        $l = ($line -replace "[;#].*$", "").Trim()
        if ($l -match "^\[(.+)\]$") { $section = $Matches[1].Trim().ToLower(); continue }
        if ($l -match "^([^=]+)=(.*)$") { $ini["$section.$($Matches[1].Trim().ToLower())"] = $Matches[2].Trim() }
    }
    return $ini
}

Write-Host "==============================================" -ForegroundColor Cyan
Write-Host "  Mega Ticket Lab - FULL REBUILD" -ForegroundColor Cyan
Write-Host "  $PSScriptRoot" -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan

if (-not (Test-Path "run.py") -or -not (Test-Path "app")) {
    Fail "run.py / app folder not found. Run this script from the mega_generator project root."
}

# ------------------------------------------------------------------ 1. stop
Step "1/7  Stopping running copies of MegaTicketLab.exe"
$running = Get-Process -Name "MegaTicketLab" -ErrorAction SilentlyContinue
if ($running) {
    $running | Stop-Process -Force
    Start-Sleep -Seconds 1
    Ok "Stopped $($running.Count) process(es)."
} else {
    Ok "None running."
}

# ----------------------------------------------------------------- 2. clean
Step "2/7  Cleaning old environment and build output"
$toRemove = @(".venv", "build", "dist", ".pytest_cache", "MegaTicketLab.spec")
foreach ($item in $toRemove) {
    if (Test-Path $item) {
        try {
            Remove-Item -Recurse -Force $item
            Ok "Removed $item"
        } catch {
            Fail "Could not remove '$item' - close PyCharm/VS Code/terminals using it and try again. ($($_.Exception.Message))"
        }
    }
}
Get-ChildItem -Path . -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch "\\\.git\\" } |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Ok "Removed __pycache__ folders"

# ------------------------------------------------------------------- 3. venv
Step "3/7  Creating virtual environment and installing packages"
$basePython = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 --version *> $null
    if ($LASTEXITCODE -eq 0) { $basePython = "py"; $baseArgs = @("-3") }
}
if (-not $basePython) {
    if (Get-Command python -ErrorAction SilentlyContinue) { $basePython = "python"; $baseArgs = @() }
    else { Fail "Python not found. Install Python 3.11+ from python.org and tick 'Add to PATH'." }
}
$ver = (& $basePython @baseArgs --version 2>&1 | ForEach-Object { "$_" }) -join " "
Ok "Using $ver"

Run $basePython ($baseArgs + @("-m", "venv", ".venv")) "creating .venv"
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { Fail ".venv was not created correctly ($py missing)." }

Run $py @("-m", "pip", "install", "--upgrade", "pip", "--quiet") "upgrading pip"
Run $py @("-m", "pip", "install", "-r", "requirements.txt", "--quiet") "installing requirements.txt"
Run $py @("-m", "pip", "install", "pyinstaller", "--quiet") "installing PyInstaller"
Ok "Packages installed."

# ------------------------------------------------------------------ 4. tests
Step "4/7  Running tests"
if ($SkipTests) {
    Warn "Skipped (-SkipTests)."
} else {
    Run $py @("-m", "pytest", "tests", "-q") "tests - fix the errors above before building"
    Ok "All tests passed."
}

# ------------------------------------------------------------------- 5. data
Step "5/7  Checking config.ini and data file"
if (-not (Test-Path "config.ini")) { Fail "config.ini not found." }
$ini = Read-Ini "config.ini"
$game = if ($ini["game.name"]) { $ini["game.name"].ToLower() } else { "mega_millions" }
$folder = if ($ini["data.folder"]) { $ini["data.folder"] } else { "data" }
$defaults = @{ "mega_millions" = "Mega_Millions_3_Year_Advanced_Pattern_Analysis.xlsx"; "powerball" = "Powerball_Draw_History.xlsx" }
$fileName = $ini["data.$($game)_filename"]
if (-not $fileName) { $fileName = $defaults[$game] }
$port = if ($ini["app.port"]) { $ini["app.port"] } else { "5000" }
$dataPath = if ([System.IO.Path]::IsPathRooted($folder)) { Join-Path $folder $fileName } else { Join-Path (Join-Path $PSScriptRoot $folder) $fileName }

Ok "Game: $game   Port: $port"
if (Test-Path $dataPath) {
    Ok "Data file found: $dataPath"
} else {
    Warn "Data file not found: $dataPath - the app will use built-in defaults until you upload a file in the browser."
}
if (-not (Test-Path "data")) { New-Item -ItemType Directory -Path "data" | Out-Null }

# ------------------------------------------------------------------ 6. build
Step "6/7  Building dist\MegaTicketLab.exe (this takes a minute)"
Run $py @(
    "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile",
    "--name", "MegaTicketLab",
    "--add-data", "app\templates;app\templates",
    "--add-data", "app\static;app\static",
    "--add-data", "config.ini;.",
    "--add-data", "data;data",
    "run.py"
) "PyInstaller build"

$exe = Join-Path $PSScriptRoot "dist\MegaTicketLab.exe"
if (-not (Test-Path $exe)) { Fail "Build finished but $exe was not found - check the PyInstaller output above." }
$sizeMb = [math]::Round((Get-Item $exe).Length / 1MB, 1)
Ok "Built $exe ($sizeMb MB)"

# ------------------------------------------------------------- 7. smoke test
Step "7/7  Smoke-testing the exe"
if ($SkipSmokeTest) {
    Warn "Skipped (-SkipSmokeTest)."
} else {
    $busy = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($busy) {
        Warn "Port $port is already in use (is 'python run.py' running?). Skipping the smoke test."
    } else {
        $proc = Start-Process -FilePath $exe -PassThru -WindowStyle Minimized
        $info = $null
        for ($i = 0; $i -lt 40 -and -not $info; $i++) {
            Start-Sleep -Milliseconds 750
            try { $info = Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/game" -TimeoutSec 2 } catch { }
        }
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        Get-Process -Name "MegaTicketLab" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
        if (-not $info) { Fail "The exe did not answer on http://127.0.0.1:$port within 30 seconds." }
        Ok "Exe answered: $($info.title) - $($info.draws_loaded) draw(s) loaded, source = $($info.source)"
        if ($info.source -ne "workbook") { Warn "Exe is using fallback data: $($info.reason)" }
    }
}

# ------------------------------------------------------------------- done
$elapsed = [math]::Round(((Get-Date) - $started).TotalSeconds)
Write-Host "`n==============================================" -ForegroundColor Green
Write-Host "  FULL REBUILD COMPLETE in $elapsed s" -ForegroundColor Green
Write-Host "  Exe:    dist\MegaTicketLab.exe" -ForegroundColor Green
Write-Host "  Dev:    .venv\Scripts\python.exe run.py" -ForegroundColor Green
Write-Host "  Open:   http://127.0.0.1:$port" -ForegroundColor Green
Write-Host "==============================================" -ForegroundColor Green

if ($Launch) {
    Write-Host "`nStarting the app - press Ctrl+C to stop." -ForegroundColor Cyan
    & $py run.py
}

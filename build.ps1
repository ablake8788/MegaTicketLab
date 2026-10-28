# build.ps1 - Builds Mega Ticket Lab into a standalone .exe
# Run this from inside the mega_generator project root.

$ErrorActionPreference = "Stop"

Write-Host "== Mega Ticket Lab build script ==" -ForegroundColor Cyan

# 1. Create venv if it doesn't exist
if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    python -m venv .venv
}

# 2. Activate venv
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
& .\.venv\Scripts\Activate.ps1

# 3. Install dependencies
Write-Host "Installing dependencies..." -ForegroundColor Yellow
pip install -r requirements.txt
pip install pyinstaller

# 4. Clean previous build artifacts
Write-Host "Cleaning old build artifacts..." -ForegroundColor Yellow
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue build, dist, MegaTicketLab.spec

# 5. Build the executable
Write-Host "Building executable with PyInstaller..." -ForegroundColor Yellow
pyinstaller --onefile `
    --add-data "app/templates;app/templates" `
    --add-data "app/static;app/static" `
    --add-data "config.ini;." `
    --add-data "data;data" `
    --name MegaTicketLab `
    run.py

# 6. Report result
$exePath = "dist\MegaTicketLab.exe"
if (Test-Path $exePath) {
    Write-Host "`nBuild succeeded!" -ForegroundColor Green
    Write-Host "Executable created at: $exePath" -ForegroundColor Green
} else {
    Write-Host "`nBuild finished but the .exe was not found. Check the PyInstaller output above for errors." -ForegroundColor Red
}

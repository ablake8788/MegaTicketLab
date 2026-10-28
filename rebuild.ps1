# rebuild.ps1 - Rebuilds the environment and runs Mega Ticket Lab.
# Run this from inside the (freshly extracted) mega_generator project root.

$ErrorActionPreference = "Stop"

Write-Host "== Mega Ticket Lab rebuild script ==" -ForegroundColor Cyan

# 1. Remove any existing venv for a clean slate
if (Test-Path ".venv") {
    Write-Host "Removing existing virtual environment..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force ".venv"
}

# 2. Create a fresh venv
Write-Host "Creating virtual environment..." -ForegroundColor Yellow
python -m venv .venv

# 3. Activate it
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
& .\.venv\Scripts\Activate.ps1

# 4. Install dependencies
Write-Host "Installing dependencies..." -ForegroundColor Yellow
pip install -r requirements.txt

# 5. Run tests
Write-Host "Running tests..." -ForegroundColor Yellow
python -m pytest tests\ -v
if ($LASTEXITCODE -ne 0) {
    Write-Host "`nTests failed. Fix the errors above before running the app." -ForegroundColor Red
    exit 1
}
Write-Host "`nTests passed." -ForegroundColor Green

# 6. Confirm the data file is present
$dataFile = "data\Mega_Millions_3_Year_Advanced_Pattern_Analysis.xlsx"
if (Test-Path $dataFile) {
    Write-Host "Historical data file found: $dataFile" -ForegroundColor Green
} else {
    Write-Host "WARNING: $dataFile not found. The app will fall back to built-in defaults instead of your real data." -ForegroundColor Red
}

# 7. Ask whether to launch the app now
$launch = Read-Host "`nLaunch the app now? (y/n)"
if ($launch -eq "y") {
    Write-Host "Starting server... open http://127.0.0.1:5000 in your browser. Press Ctrl+C to stop." -ForegroundColor Cyan
    python run.py
} else {
    Write-Host "`nDone. Run 'python run.py' whenever you're ready to start the app." -ForegroundColor Green
}

# =====================================================================
#  Week 1 Demo Launcher - Module 1 (Core Data) + Module 13 (Data Integration)
#
#  Usage:
#      powershell -ExecutionPolicy Bypass -File .\run_week1_demo.ps1
#
#  What this script does:
#      1) Prepares the SQLite database (tables are created by init_db)
#      2) Loads Module 1 sample data using the existing seed_data.py
#      3) Starts the demo app: uvicorn demo_week1:app
#      4) Opens http://127.0.0.1:8000/docs in the default browser
#
#  NOTE: This script only READS the project. It does not modify main.py,
#        app/, tests/, sample_data/ or any existing seed file.
#
#  NOTE: Text is intentionally ASCII-only so the output renders correctly
#        in Windows PowerShell 5.1 consoles regardless of code page.
# =====================================================================

$ErrorActionPreference = "Stop"

# Always run from the folder that contains this script (backend root).
Set-Location -Path $PSScriptRoot

$Port = 8000
$DocsUrl = "http://127.0.0.1:$Port/docs"

function Write-Step {
    param([string]$Text)
    Write-Host ""
    Write-Host "==> $Text" -ForegroundColor Cyan
}

function Write-Ok {
    param([string]$Text)
    Write-Host "    OK - $Text" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Text)
    Write-Host "    ! $Text" -ForegroundColor Yellow
}

Write-Host "======================================================" -ForegroundColor White
Write-Host " Week 1 Demo - Core Data and Data Integration" -ForegroundColor White
Write-Host " Modules: 1 (University Structure) + 13 (Data Import)" -ForegroundColor White
Write-Host "======================================================" -ForegroundColor White

# ---------------------------------------------------------------------
# 0) Resolve the Python interpreter
# ---------------------------------------------------------------------
Write-Step "Locating Python interpreter"

$VenvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (Test-Path $VenvPython) {
    $Python = $VenvPython
    Write-Ok "Using virtual environment: .venv\Scripts\python.exe"
}
else {
    $Python = "python"
    Write-Warn ".venv not found, falling back to the system 'python'"
}

# Verify the interpreter actually runs.
try {
    $PyVersion = & $Python --version 2>&1
    Write-Ok "$PyVersion"
}
catch {
    Write-Host ""
    Write-Host "ERROR: Python could not be started." -ForegroundColor Red
    Write-Host "       Create the virtual environment and install dependencies:" -ForegroundColor Red
    Write-Host "           python -m venv .venv" -ForegroundColor Red
    Write-Host "           .venv\Scripts\Activate.ps1" -ForegroundColor Red
    Write-Host "           pip install -r requirements.txt" -ForegroundColor Red
    exit 1
}

# ---------------------------------------------------------------------
# 1) Check required packages
# ---------------------------------------------------------------------
Write-Step "Checking required packages"

& $Python -c "import fastapi, uvicorn, sqlalchemy, pydantic_settings, pandas, openpyxl, multipart" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "ERROR: Required packages are missing." -ForegroundColor Red
    Write-Host "       Run: pip install -r requirements.txt" -ForegroundColor Red
    exit 1
}
Write-Ok "fastapi, uvicorn, sqlalchemy, pydantic-settings, pandas, openpyxl, python-multipart"

# ---------------------------------------------------------------------
# 2) Verify the demo entry point and sample files exist
# ---------------------------------------------------------------------
Write-Step "Verifying demo files"

if (-not (Test-Path (Join-Path $PSScriptRoot "demo_week1.py"))) {
    Write-Host "ERROR: demo_week1.py not found in $PSScriptRoot" -ForegroundColor Red
    exit 1
}
Write-Ok "demo_week1.py"

if (-not (Test-Path (Join-Path $PSScriptRoot "seed_data.py"))) {
    Write-Host "ERROR: seed_data.py not found in $PSScriptRoot" -ForegroundColor Red
    exit 1
}
Write-Ok "seed_data.py"

$DemoFiles = @(
    "sample_data\faculties_sample.csv",
    "sample_data\faculties_sample.xlsx",
    "sample_data\departments_sample.csv",
    "sample_data\programs_sample.csv",
    "sample_data\administrative_units_sample.csv",
    "sample_data\faculties_with_errors_sample.csv"
)

foreach ($File in $DemoFiles) {
    if (Test-Path (Join-Path $PSScriptRoot $File)) {
        Write-Ok $File
    }
    else {
        Write-Warn "MISSING: $File (this demo step will not be available)"
    }
}

# ---------------------------------------------------------------------
# 3) Prepare the database and load Module 1 sample data
#    seed_data.py calls init_db() first, so the tables are created here.
#    The script is idempotent: running it again does not duplicate records.
# ---------------------------------------------------------------------
Write-Step "Preparing database and loading Module 1 sample data"

& $Python seed_data.py
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "ERROR: seed_data.py failed. The demo cannot start." -ForegroundColor Red
    exit 1
}
Write-Ok "Database ready (university_management.db)"
Write-Ok "Module 1 records: FEA / SWE / CENG / SWE-BSC / CENG-BSC / ERASMUS"

# ---------------------------------------------------------------------
# 4) Open the browser shortly after the server starts
#    A background job is used so the browser opens once uvicorn is up.
# ---------------------------------------------------------------------
Write-Step "Scheduling browser launch"

Start-Job -ScriptBlock {
    param($Url)
    Start-Sleep -Seconds 4
    Start-Process $Url
} -ArgumentList $DocsUrl | Out-Null

Write-Ok "Browser will open $DocsUrl in ~4 seconds"

# ---------------------------------------------------------------------
# 5) Start the demo application
# ---------------------------------------------------------------------
Write-Step "Starting the demo application"

Write-Host ""
Write-Host "  Swagger UI : $DocsUrl" -ForegroundColor White
Write-Host "  OpenAPI    : http://127.0.0.1:$Port/openapi.json" -ForegroundColor White
Write-Host "  Health     : http://127.0.0.1:$Port/health" -ForegroundColor White
Write-Host "  Demo info  : http://127.0.0.1:$Port/demo-info" -ForegroundColor White
Write-Host ""
Write-Host "  Enabled  : Module 1 (faculties, departments, programs, administrative units)" -ForegroundColor White
Write-Host "             Module 13 (data integration)" -ForegroundColor White
Write-Host "  Disabled : Module 2, Module 9, Module 10" -ForegroundColor White
Write-Host ""
Write-Host "  Press CTRL+C to stop the server." -ForegroundColor Yellow
Write-Host ""

& $Python -m uvicorn demo_week1:app --reload --host 127.0.0.1 --port $Port

# ---------------------------------------------------------------------
# 6) Cleanup after the server stops
# ---------------------------------------------------------------------
Write-Host ""
Write-Step "Demo stopped"
Get-Job | Remove-Job -Force -ErrorAction SilentlyContinue
Write-Ok "Background jobs cleaned up"

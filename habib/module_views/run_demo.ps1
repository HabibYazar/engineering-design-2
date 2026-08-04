# =====================================================================
#  module_views Standalone Demo Launcher
#  Module 1 (Core Data) + Module 13 (Data Integration)
#
#  Usage (from inside the module_views folder):
#      powershell -ExecutionPolicy Bypass -File .\run_demo.ps1
#
#  What this script does:
#      1) Checks the required packages
#      2) Prepares the demo SQLite database (module_views\demo_module_views.db)
#      3) Loads Module 1 seed data
#      4) Starts the app with: uvicorn main:app --reload
#
#  This demo is fully standalone: it imports nothing from backend/app.
#
#  NOTE: Text is intentionally ASCII-only so the output renders correctly
#        in Windows PowerShell 5.1 consoles regardless of code page.
# =====================================================================

$ErrorActionPreference = "Stop"

# Always run from the folder that contains this script (module_views).
Set-Location -Path $PSScriptRoot

$Port = 8000
$DocsUrl = "http://127.0.0.1:$Port/docs"

function Write-Step { param([string]$Text); Write-Host ""; Write-Host "==> $Text" -ForegroundColor Cyan }
function Write-Ok   { param([string]$Text); Write-Host "    OK - $Text" -ForegroundColor Green }
function Write-Warn { param([string]$Text); Write-Host "    ! $Text" -ForegroundColor Yellow }
function Write-Err  { param([string]$Text); Write-Host "ERROR: $Text" -ForegroundColor Red }

Write-Host "======================================================" -ForegroundColor White
Write-Host " module_views Standalone Demo" -ForegroundColor White
Write-Host " Module 1 (Core Data) + Module 13 (Data Integration)" -ForegroundColor White
Write-Host "======================================================" -ForegroundColor White

# ---------------------------------------------------------------------
# 0) Resolve the Python interpreter
# ---------------------------------------------------------------------
Write-Step "Locating Python interpreter"

$VenvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (Test-Path $VenvPython) {
    $Python = $VenvPython
    Write-Ok "Using local virtual environment: .venv\Scripts\python.exe"
}
else {
    $Python = "python"
    Write-Warn ".venv not found in module_views, using the system 'python'"
    Write-Warn "To create one:  python -m venv .venv"
}

try {
    $PyVersion = & $Python --version 2>&1
    Write-Ok "$PyVersion"
}
catch {
    Write-Err "Python could not be started."
    Write-Host "       python -m venv .venv" -ForegroundColor Red
    Write-Host "       .\.venv\Scripts\Activate.ps1" -ForegroundColor Red
    Write-Host "       python -m pip install -r requirements.txt" -ForegroundColor Red
    exit 1
}

# ---------------------------------------------------------------------
# 1) Check required packages
# ---------------------------------------------------------------------
Write-Step "Checking required packages"

$Checks = @(
    @{ Import = "fastapi";    Package = "fastapi" },
    @{ Import = "uvicorn";    Package = "uvicorn[standard]" },
    @{ Import = "sqlalchemy"; Package = "sqlalchemy" },
    @{ Import = "pydantic";   Package = "pydantic" },
    @{ Import = "multipart";  Package = "python-multipart" },
    @{ Import = "pandas";     Package = "pandas" },
    @{ Import = "openpyxl";   Package = "openpyxl" }
)

$Missing = @()
foreach ($Check in $Checks) {
    & $Python -c "import $($Check.Import)" 2>$null
    if ($LASTEXITCODE -eq 0) { Write-Ok $Check.Package }
    else { Write-Warn "MISSING: $($Check.Package)"; $Missing += $Check.Package }
}

if ($Missing.Count -gt 0) {
    Write-Step "Installing missing packages"
    & $Python -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Package installation failed."
        Write-Host "       Run manually: python -m pip install -r requirements.txt" -ForegroundColor Red
        exit 1
    }
    Write-Ok "Dependencies installed"
}

# ---------------------------------------------------------------------
# 2) Verify demo files
# ---------------------------------------------------------------------
Write-Step "Verifying demo files"

$RequiredPaths = @(
    "main.py",
    "requirements.txt",
    "module_01_core_data\models\faculty.py",
    "module_01_core_data\schemas\faculty.py",
    "module_01_core_data\routers\faculties.py",
    "module_01_core_data\services\crud_helpers.py",
    "module_01_core_data\seed_data.py",
    "module_13_data_integration\models\import_job.py",
    "module_13_data_integration\schemas\data_integration.py",
    "module_13_data_integration\routers\data_integration.py",
    "module_13_data_integration\services\file_parser.py",
    "module_13_data_integration\services\import_validators.py",
    "module_13_data_integration\services\import_service.py"
)

$MissingFiles = @()
foreach ($Path in $RequiredPaths) {
    if (Test-Path (Join-Path $PSScriptRoot $Path)) { Write-Ok $Path }
    else { Write-Err "MISSING: $Path"; $MissingFiles += $Path }
}

if ($MissingFiles.Count -gt 0) {
    Write-Err "Required files are missing. The demo cannot start."
    exit 1
}

# Sample data files used in the demo flow
Write-Step "Checking sample data files"

$SampleFiles = @(
    "module_13_data_integration\sample_data\faculties_sample.csv",
    "module_13_data_integration\sample_data\faculties_sample.xlsx",
    "module_13_data_integration\sample_data\departments_sample.csv",
    "module_13_data_integration\sample_data\programs_sample.csv",
    "module_13_data_integration\sample_data\administrative_units_sample.csv",
    "module_13_data_integration\sample_data\faculties_with_errors_sample.csv"
)

foreach ($File in $SampleFiles) {
    if (Test-Path (Join-Path $PSScriptRoot $File)) { Write-Ok (Split-Path $File -Leaf) }
    else { Write-Warn "MISSING: $File (this demo step will not be available)" }
}

# ---------------------------------------------------------------------
# 3) Prepare the database and load seed data
#    prepare_demo.py is generated on the fly so the logic stays in main.py.
# ---------------------------------------------------------------------
Write-Step "Preparing database and loading Module 1 seed data"

$PrepareCode = @'
import main
main.init_db()
print("[run_demo] Database ready:", main.DB_PATH)
if main.load_seed_data():
    print("[run_demo] Module 1 seed data loaded")
print("[run_demo] Loaded python files:", len(main.LOADED_FILES))
for table, exists in main.verify_required_tables().items():
    print(f"[run_demo]   {table}: {'OK' if exists else 'MISSING'}")
'@

$PrepareCode | & $Python -
if ($LASTEXITCODE -ne 0) {
    Write-Err "Database preparation failed."
    exit 1
}
Write-Ok "Database and seed data ready"

# ---------------------------------------------------------------------
# 4) Open the browser shortly after the server starts
# ---------------------------------------------------------------------
Write-Step "Scheduling browser launch"

Start-Job -ScriptBlock {
    param($Url)
    Start-Sleep -Seconds 4
    Start-Process $Url
} -ArgumentList $DocsUrl | Out-Null

Write-Ok "Browser will open $DocsUrl in ~4 seconds"

# ---------------------------------------------------------------------
# 5) Start the application
# ---------------------------------------------------------------------
Write-Step "Starting the demo application"

Write-Host ""
Write-Host "  Swagger UI : $DocsUrl" -ForegroundColor White
Write-Host "  OpenAPI    : http://127.0.0.1:$Port/openapi.json" -ForegroundColor White
Write-Host "  Health     : http://127.0.0.1:$Port/health" -ForegroundColor White
Write-Host "  Demo info  : http://127.0.0.1:$Port/demo-info" -ForegroundColor White
Write-Host ""
Write-Host "  Enabled  : Faculties, Departments, Academic Programs," -ForegroundColor White
Write-Host "             Administrative Units, Data Integration, Health" -ForegroundColor White
Write-Host "  Excluded : Student Analytics, Scenario Analysis, Ranking Evaluations" -ForegroundColor White
Write-Host ""
Write-Host "  Press CTRL+C to stop the server." -ForegroundColor Yellow
Write-Host ""

& $Python -m uvicorn main:app --reload --host 127.0.0.1 --port $Port

# ---------------------------------------------------------------------
# 6) Cleanup
# ---------------------------------------------------------------------
Write-Host ""
Write-Step "Demo stopped"
Get-Job | Remove-Job -Force -ErrorAction SilentlyContinue
Write-Ok "Background jobs cleaned up"

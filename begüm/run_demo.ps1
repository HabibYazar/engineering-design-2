# Modul 3-7-11 demosunu tek komutla baslatir.
#
# Kullanim:
#   powershell -ExecutionPolicy Bypass -File .\run_demo.ps1
#
# Yaptigi isler:
#   1. Gerekli paketleri kontrol eder, eksikse kurar
#   2. Istege bagli olarak veritabanini sifirlar
#   3. Sunucuyu baslatir

param(
    [switch]$Reset  # -Reset verilirse demo.db silinir ve veri bastan uretilir
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

Write-Host "=== Modul 3, 7, 11 - Demo Baslatiliyor ===" -ForegroundColor Cyan

# --- 1. Paket kontrolu ---
Write-Host "`n[1/3] Paketler kontrol ediliyor..."
$eksik = @()
foreach ($paket in @("fastapi", "uvicorn", "sqlalchemy", "pydantic")) {
    python -c "import $paket" 2>$null
    if (-not $?) { $eksik += $paket }
}

if ($eksik.Count -gt 0) {
    Write-Host "      Eksik paketler: $($eksik -join ', ') - kuruluyor..." -ForegroundColor Yellow
    python -m pip install -r requirements.txt
} else {
    Write-Host "      Tum paketler mevcut." -ForegroundColor Green
}

# --- 2. Veritabani ---
Write-Host "`n[2/3] Veritabani hazirlaniyor..."
if ($Reset -and (Test-Path "demo.db")) {
    Remove-Item "demo.db" -Force
    Write-Host "      demo.db silindi, veri bastan uretilecek." -ForegroundColor Yellow
} elseif (Test-Path "demo.db") {
    Write-Host "      Mevcut demo.db kullanilacak (sifirlamak icin: .\run_demo.ps1 -Reset)."
} else {
    Write-Host "      demo.db bulunamadi, ilk aciliste olusturulacak."
}

# --- 3. Sunucu ---
Write-Host "`n[3/3] Sunucu baslatiliyor..."
Write-Host "      Adres: http://127.0.0.1:8000/docs" -ForegroundColor Green
Write-Host "      Durdurmak icin: Ctrl+C`n"

python main.py

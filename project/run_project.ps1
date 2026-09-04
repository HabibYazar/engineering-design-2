<#
.SYNOPSIS
    Birleştirilmiş Stratejik Üniversite Yönetimi ve Karar Destek Sistemi'ni
    tek komutla kurar, veriyi yükler ve çalıştırır.

.DESCRIPTION
    Sırayla:
      1. Python sürümünü kontrol eder
      2. Sanal ortamı oluşturur/etkinleştirir
      3. Bağımlılıkları kurar
      4. Ortak demo verisini yükler (idempotent — tekrar çalıştırmak güvenlidir)
      5. Testleri çalıştırır (isteğe bağlı)
      6. Sunucuyu başlatır ve tarayıcıyı açar

.PARAMETER SkipInstall
    Bağımlılık kurulumunu atlar. Ortam hazırsa başlangıcı hızlandırır.

.PARAMETER Seed
    Örnek demo verisini yükler. Teslim veritabanı zaten gerçek veriyle
    dolu olduğu için normalde GEREKMEZ.

.PARAMETER RunTests
    Sunucuyu başlatmadan önce 432 testi çalıştırır.

.PARAMETER FreshDatabase
    Mevcut veritabanını siler ve sıfırdan oluşturur.
    DİKKAT: Girilen tüm veriler kaybolur.

.PARAMETER Port
    Sunucu portu. Varsayılan 8000.

.EXAMPLE
    .\run_project.ps1
    Normal başlatma.

.EXAMPLE
    .\run_project.ps1 -FreshDatabase -RunTests
    Sıfırdan kurulum + tam doğrulama. Sunum öncesi önerilir.

.EXAMPLE
    .\run_project.ps1 -SkipInstall
    Hızlı yeniden başlatma.
#>

[CmdletBinding()]
param(
    [switch]$SkipInstall,
    [switch]$Seed,
    [switch]$RunTests,
    [switch]$FreshDatabase,
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

# Script nerede olursa olsun doğru klasörleri bulsun diye kendi konumundan yola çıkıyoruz.
$RootDir     = Split-Path -Parent $MyInvocation.MyCommand.Path
# TESLIM YAPISI: backend ve frontend bu script ile AYNI klasörde.
# (Geliştirme deposunda araya bir "integration" katmanı giriyordu.)
$BackendDir  = Join-Path $RootDir "backend"
$FrontendDir = Join-Path $RootDir "frontend"
$VenvDir     = Join-Path $RootDir ".venv"

function Write-Step {
    param([string]$Number, [string]$Text)
    Write-Host ""
    Write-Host "[$Number] $Text" -ForegroundColor Cyan
}

function Write-Ok    { param([string]$T) Write-Host "      $T" -ForegroundColor Green }
function Write-Warn2 { param([string]$T) Write-Host "      $T" -ForegroundColor Yellow }
function Write-Err2  { param([string]$T) Write-Host "      $T" -ForegroundColor Red }

Write-Host ""
Write-Host "===============================================================" -ForegroundColor White
Write-Host " Stratejik Universite Yonetimi ve Karar Destek Sistemi" -ForegroundColor White
Write-Host " Birlestirilmis urun - 13 modul, tek backend, tek arayuz" -ForegroundColor White
Write-Host "===============================================================" -ForegroundColor White

# --------------------------------------------------------------------------
# 0) Klasör kontrolü
# --------------------------------------------------------------------------
Write-Step "0/7" "Proje yapisi kontrol ediliyor"

if (-not (Test-Path $BackendDir)) {
    Write-Err2 "Backend klasoru bulunamadi: $BackendDir"
    Write-Err2 "Bu script'i deponun kok klasorunden calistirin."
    exit 1
}
if (-not (Test-Path $FrontendDir)) {
    Write-Warn2 "Arayuz klasoru bulunamadi: $FrontendDir"
    Write-Warn2 "Backend calisir ancak web arayuzu acilmaz."
}
Write-Ok "Backend : $BackendDir"
Write-Ok "Arayuz  : $FrontendDir"

# --------------------------------------------------------------------------
# 1) Python
# --------------------------------------------------------------------------
Write-Step "1/7" "Python surumu kontrol ediliyor"

try {
    $pythonVersion = & python --version 2>&1
} catch {
    Write-Err2 "Python bulunamadi. https://www.python.org adresinden kurun"
    Write-Err2 "ve kurulum sirasinda 'Add Python to PATH' secenegini isaretleyin."
    exit 1
}

# Proje Python 3.10+ soz dizimi kullaniyor (X | Y tip birlesimleri, match yok).
if ($pythonVersion -match "Python (\d+)\.(\d+)") {
    $major = [int]$Matches[1]
    $minor = [int]$Matches[2]
    if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 10)) {
        Write-Err2 "$pythonVersion bulundu ancak Python 3.10 veya ustu gerekiyor."
        exit 1
    }
}
Write-Ok "$pythonVersion"

# --------------------------------------------------------------------------
# 2) Sanal ortam
# --------------------------------------------------------------------------
Write-Step "2/7" "Sanal ortam hazirlaniyor"

if (-not (Test-Path $VenvDir)) {
    Write-Ok "Sanal ortam olusturuluyor (.venv)..."
    & python -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { Write-Err2 "Sanal ortam olusturulamadi."; exit 1 }
}

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    # Linux/macOS uzerinde PowerShell Core ile calistirilirsa.
    $VenvPython = Join-Path $VenvDir "bin/python"
}
if (-not (Test-Path $VenvPython)) {
    Write-Err2 "Sanal ortamdaki Python bulunamadi: $VenvPython"
    exit 1
}
Write-Ok "Sanal ortam hazir: $VenvDir"

# --------------------------------------------------------------------------
# 3) Bağımlılıklar
# --------------------------------------------------------------------------
Write-Step "3/7" "Bagimliliklar"

if ($SkipInstall) {
    Write-Warn2 "-SkipInstall verildi, kurulum atlandi."
} else {
    $req = Join-Path $BackendDir "requirements.txt"
    if (-not (Test-Path $req)) {
        Write-Err2 "requirements.txt bulunamadi: $req"
        exit 1
    }
    & $VenvPython -m pip install --upgrade pip --quiet
    & $VenvPython -m pip install -r $req --quiet
    if ($LASTEXITCODE -ne 0) { Write-Err2 "Bagimliliklar kurulamadi."; exit 1 }
    Write-Ok "Bagimliliklar kuruldu."
}

# --------------------------------------------------------------------------
# 4) Veritabanı ve demo verisi
# --------------------------------------------------------------------------
Write-Step "4/7" "Veritabani ve ortak demo verisi"

Push-Location $BackendDir
try {
    if ($FreshDatabase) {
        Get-ChildItem -Path $BackendDir -Filter "*.db" -ErrorAction SilentlyContinue |
            ForEach-Object {
                Remove-Item $_.FullName -Force
                Write-Warn2 "Silindi: $($_.Name)"
            }
    }

    # TESLIM PAKETINDE VERITABANI HAZIR GELIR.
    # university_management.db gercek kurum verisiyle doludur
    # (2020-2026 YKS, akademik kadro, ogrenci, finans, mufredat).
    # Demo seed VARSAYILAN OLARAK CALISMAZ; istenirse -Seed ile.
    if ($Seed) {
        Write-Warn2 "-Seed verildi: ornek demo verisi yukleniyor..."
        & $VenvPython seed_all_demo_data.py
        if ($LASTEXITCODE -ne 0) { Write-Err2 "Veri yuklenemedi."; exit 1 }
    } else {
        Write-Ok "Hazir veritabani kullaniliyor (university_management.db)."
    }

    # ----------------------------------------------------------------------
    # 5) Testler
    # ----------------------------------------------------------------------
    Write-Step "5/7" "Testler"

    if ($RunTests) {
        Write-Ok "Birim ve entegrasyon testleri calistiriliyor..."
        & $VenvPython -m pytest tests tests_integration -q
        if ($LASTEXITCODE -ne 0) {
            Write-Err2 "TESTLER BASARISIZ. Sunucu yine de baslatilacak,"
            Write-Err2 "ancak sunuma girmeden once hatalari inceleyin."
        } else {
            Write-Ok "Tum testler gecti."
        }
    } else {
        Write-Warn2 "Testler atlandi. Calistirmak icin: .\run_project.ps1 -RunTests"
    }

    # ----------------------------------------------------------------------
    # 6) Akilli Asistan - yerel dil modeli (Ollama)
    # ----------------------------------------------------------------------
    # Ollama kapaliysa proje DURDURULMAZ. Yalnizca Akilli Asistan ekrani
    # devre disi baslar; diger 15 ekran normal calisir.
    #
    # Ollama'yi otomatik baslatmayi DENEMEYIZ: servis yonetici yetkisi
    # gerektirebilir ve kullanicinin makinesinde arka plan servisi baslatmak
    # bu betigin isi degil.
    Write-Step "6/7" "Yapay Zeka Kokpiti (Google Gemini)"

    # Anahtar yoksa proje DURDURULMAZ. Yalnizca Yapay Zeka Kokpiti ekrani
    # "saglayici yapilandirilmadi" durumunu gosterir; diger ekranlar
    # normal calisir. Burada GERCEK BIR API ISTEGI YAPILMAZ; yalnizca
    # .env dosyasinin varligi ve anahtar alaninin doldurulup
    # doldurulmadigi kontrol edilir (kota harcanmaz).
    $EnvFile = Join-Path $BackendDir ".env"
    if (-not (Test-Path $EnvFile)) {
        Write-Warn2 "Uyari: .env bulunamadi. Yapay Zeka Kokpiti devre disi baslar."
        Write-Warn2 "  Etkinlestirmek icin: copy .env.example .env"
        Write-Warn2 "  Ardindan GEMINI_API_KEY satirina kendi anahtarinizi yazin."
    } else {
        $anahtar = (Select-String -Path $EnvFile -Pattern '^GEMINI_API_KEY=(.+)$').Matches.Groups[1].Value
        if ([string]::IsNullOrWhiteSpace($anahtar) -or $anahtar -eq "YOUR_KEY_HERE") {
            Write-Warn2 "Uyari: GEMINI_API_KEY doldurulmamis."
            Write-Warn2 "  Yapay Zeka Kokpiti devre disi baslar, proje calisir."
        } else {
            Write-Ok "Gemini anahtari tanimli. Yapay Zeka Kokpiti hazir."
        }
    }

    # ----------------------------------------------------------------------
    # 7) Sunucu
    # ----------------------------------------------------------------------
    Write-Step "7/7" "Sunucu baslatiliyor"

    $url = "http://127.0.0.1:$Port"
    Write-Host ""
    Write-Host "  Web arayuzu     : $url" -ForegroundColor Green
    Write-Host "  API dokumani    : $url/docs" -ForegroundColor Green
    Write-Host "  Saglik kontrolu : $url/health" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Demo hesaplari (parola: demo1234)" -ForegroundColor Gray
    Write-Host "    admin          - tum kurum + kullanici yonetimi" -ForegroundColor Gray
    Write-Host "    dekan.muh      - Muhendislik ve Mimarlik Fakultesi" -ForegroundColor Gray
    Write-Host "    baskan.ceng    - Bilgisayar Muhendisligi Bolumu" -ForegroundColor Gray
    Write-Host "    ogretim.uyesi  - yalnizca goruntuleme" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  Durdurmak icin Ctrl+C" -ForegroundColor Yellow
    Write-Host ""

    # Sunucu hazir olunca tarayiciyi ac. Uvicorn'u onceden acmak bos sayfa
    # gosterirdi; bu yuzden ayri bir is olarak gecikmeli aciliyor.
    Start-Job -ScriptBlock {
        param($u)
        Start-Sleep -Seconds 3
        Start-Process $u
    } -ArgumentList $url | Out-Null

    & $VenvPython -m uvicorn main:app --host 127.0.0.1 --port $Port
}
finally {
    Pop-Location
    Get-Job | Remove-Job -Force -ErrorAction SilentlyContinue
}

# ============================================================
# LBAMonitor — Script de build completo
# Compila backend + desktop + genera instalador MSI + portable ZIP
# ============================================================

param(
    [string]$Version = "1.0.0",
    [switch]$SkipFrontend,
    [switch]$SkipInstaller,
    [switch]$SkipPortable
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")

function Write-Step($msg) {
    Write-Host ""
    Write-Host "=== $msg ===" -ForegroundColor Cyan
}

# 1. Frontend
if (-not $SkipFrontend) {
    Write-Step "Compilando frontend React"
    Push-Location (Join-Path $ProjectRoot "frontend")
    npm install --no-fund --no-audit
    npm run build
    Pop-Location
}

# 2. Backend (PyInstaller)
Write-Step "Compilando backend con PyInstaller"
Push-Location (Join-Path $ProjectRoot "backend")
$env:PYTHONPATH = (Get-Location).Path
pyinstaller (Join-Path $ProjectRoot "installer\pyinstaller\svc.spec") --noconfirm --distpath (Join-Path $ProjectRoot "installer\build")
pyinstaller (Join-Path $ProjectRoot "installer\pyinstaller\cli.spec") --noconfirm --distpath (Join-Path $ProjectRoot "installer\build")
Pop-Location

# 3. Desktop (PyInstaller)
Write-Step "Compilando desktop admin con PyInstaller"
Push-Location (Join-Path $ProjectRoot "desktop")
$env:PYTHONPATH = (Join-Path $ProjectRoot "backend") + ";" + (Get-Location).Path
pyinstaller (Join-Path $ProjectRoot "installer\pyinstaller\desktop.spec") --noconfirm --distpath (Join-Path $ProjectRoot "installer\build")
Pop-Location

# 4. Instalador MSI
if (-not $SkipInstaller) {
    Write-Step "Generando instalador con Inno Setup"
    $IssPath = Join-Path $ProjectRoot "installer\msi\lbamonitor.iss"
    if (Get-Command "iscc" -ErrorAction SilentlyContinue) {
        iscc $IssPath
    } else {
        $IsccPath = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
        if (Test-Path $IsccPath) {
            & $IsccPath $IssPath
        } else {
            Write-Host "Inno Setup no encontrado. Instálalo de https://jrsoftware.org/isdl.php" -ForegroundColor Yellow
        }
    }
}

# 5. Portable ZIP
if (-not $SkipPortable) {
    Write-Step "Generando version portable"
    $PortableScript = Join-Path $ProjectRoot "installer\portable\build.ps1"
    & powershell -ExecutionPolicy Bypass -File $PortableScript -Version $Version
}

Write-Host ""
Write-Host "================================" -ForegroundColor Green
Write-Host "BUILD COMPLETADO" -ForegroundColor Green
Write-Host "================================" -ForegroundColor Green
Write-Host "Artifacts en: $ProjectRoot\installer\build\" -ForegroundColor Gray

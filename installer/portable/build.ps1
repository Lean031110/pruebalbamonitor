# ============================================================
# LBAMonitor — Script para generar versión portable (ZIP)
# ============================================================

param(
    [string]$Version = "1.0.0",
    [string]$OutputDir = "..\build\portable"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$BuildDir = Join-Path $ProjectRoot "installer\build"
$PortableDir = Join-Path $OutputDir "LBAMonitor-Portable-$Version"

Write-Host "[LBAMonitor] Generando versión portable $Version..." -ForegroundColor Cyan

# Crear directorio temporal
if (Test-Path $PortableDir) {
    Remove-Item $PortableDir -Recurse -Force
}
New-Item -ItemType Directory -Path $PortableDir -Force | Out-Null

# Copiar backend build
$SvcBuild = Join-Path $BuildDir "lbamonitor-svc"
if (Test-Path $SvcBuild) {
    Write-Host "  Copiando lbamonitor-svc..."
    Copy-Item $SvcBuild $PortableDir -Recurse
} else {
    Write-Host "  Advertencia: $SvcBuild no existe. Ejecuta PyInstaller primero." -ForegroundColor Yellow
}

# Copiar CLI build
$CliBuild = Join-Path $BuildDir "lbamonitor-cli"
if (Test-Path $CliBuild) {
    Write-Host "  Copiando lbamonitor-cli..."
    Copy-Item $CliBuild $PortableDir -Recurse
}

# Copiar desktop build
$DesktopBuild = Join-Path $BuildDir "lbamonitor-desktop"
if (Test-Path $DesktopBuild) {
    Write-Host "  Copiando lbamonitor-desktop..."
    Copy-Item $DesktopBuild $PortableDir -Recurse
}

# Copiar config default
$ConfigFile = Join-Path $ProjectRoot "config.default.toml"
if (Test-Path $ConfigFile) {
    Copy-Item $ConfigFile $PortableDir
}

# Crear README portable
$Readme = Join-Path $PortableDir "README-PORTABLE.txt"
@"
LBAMonitor Portable v$Version
==============================

Esta es la versión portable de LBAMonitor. No requiere instalación.

USO:
  1. Ejecuta start-svc.bat para arrancar el servicio (API + monitor USB).
  2. Ejecuta start-desktop.bat para abrir la app de administración.
  3. Opcional: abre http://127.0.0.1:8123 en tu navegador.

NOTAS:
  - Los datos se guardan en .\data\ (subcarpeta del portable).
  - Los logs en .\logs\
  - Los backups en .\backups\
  - Para cambiar config, edita config.toml (creado al primer arranque).

LIMITACIONES:
  - No se registra como servicio Windows (no auto-start con el PC).
  - No hay icono de bandeja si no se ejecuta el desktop.
"@ | Out-File -Encoding UTF8 $Readme

# Crear start-svc.bat
$StartSvc = Join-Path $PortableDir "start-svc.bat"
@"
@echo off
cd /d "%~dp0"
echo Iniciando LBAMonitor Servicio...
lbamonitor-svc\lbamonitor-svc.exe
pause
"@ | Out-File -Encoding ASCII $StartSvc

# Crear start-desktop.bat
$StartDesktop = Join-Path $PortableDir "start-desktop.bat"
@"
@echo off
cd /d "%~dp0"
echo Iniciando LBAMonitor Desktop...
start "" lbamonitor-desktop\lbamonitor-desktop.exe
"@ | Out-File -Encoding ASCII $StartDesktop

# Crear ZIP
$ZipPath = Join-Path $OutputDir "LBAMonitor-Portable-$Version.zip"
if (Test-Path $ZipPath) {
    Remove-Item $ZipPath -Force
}

Write-Host "  Comprimiendo a ZIP..." -ForegroundColor Cyan
Compress-Archive -Path "$PortableDir\*" -DestinationPath $ZipPath -CompressionLevel Optimal

# Limpiar directorio temporal
Remove-Item $PortableDir -Recurse -Force

Write-Host ""
Write-Host "Version portable generada:" -ForegroundColor Green
Write-Host "  $ZipPath" -ForegroundColor Green
$Size = (Get-Item $ZipPath).Length / 1MB
Write-Host "  Tamano: $([math]::Round($Size, 2)) MB" -ForegroundColor Gray

# ============================================================
# LBAMonitor — Script de instalación del servicio Windows
# Usa NSSM para registrar lbamonitor-svc.exe como servicio.
# ============================================================

param(
    [string]$ServiceName = "LBAMonitorService",
    [string]$AppDir = "C:\Program Files\LBAMonitor",
    [string]$DataDir = "C:\ProgramData\LBAMonitor",
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"

function Write-Step($msg) {
    Write-Host "[LBAMonitor] $msg" -ForegroundColor Cyan
}

function Test-Admin {
    $currentUser = [Security.Principal.WindowsPrincipal][Security.Principal]::GetCurrent()
    return $currentUser.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Admin)) {
    Write-Host "Este script requiere permisos de administrador." -ForegroundColor Red
    Write-Host "Ejecuta PowerShell como administrador y vuelve a intentarlo." -ForegroundColor Yellow
    exit 1
}

# Localizar nssm.exe
$Nssm = Join-Path $AppDir "nssm.exe"
if (-not (Test-Path $Nssm)) {
    # Buscar en PATH
    $Nssm = Get-Command "nssm.exe" -ErrorAction SilentlyContinue
    if (-not $Nssm) {
        Write-Host "nssm.exe no encontrado. Descárgalo de https://nssm.cc" -ForegroundColor Red
        exit 1
    }
    $Nssm = $Nssm.Source
}

if ($Uninstall) {
    Write-Step "Deteniendo servicio $ServiceName..."
    & $Nssm stop $ServiceName 2>$null
    Start-Sleep -Seconds 2

    Write-Step "Eliminando servicio $ServiceName..."
    & $Nssm remove $ServiceName confirm
    Write-Host "Servicio eliminado." -ForegroundColor Green
    exit 0
}

# Crear directorios de datos si no existen
$Dirs = @("data", "logs", "backups", "exports", "config")
foreach ($d in $Dirs) {
    $path = Join-Path $DataDir $d
    if (-not (Test-Path $path)) {
        Write-Step "Creando $path"
        New-Item -ItemType Directory -Path $path -Force | Out-Null
    }
}

# Copiar config default si no existe config.toml
$ConfigFile = Join-Path $DataDir "config\config.toml"
$DefaultConfig = Join-Path $AppDir "config.default.toml"
if (-not (Test-Path $ConfigFile) -and (Test-Path $DefaultConfig)) {
    Write-Step "Copiando config default a $ConfigFile"
    Copy-Item $DefaultConfig $ConfigFile
}

# Verificar si el servicio ya existe
$existingService = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existingService) {
    Write-Step "El servicio $ServiceName ya existe. Reconfigurando..."
    & $Nssm stop $ServiceName 2>$null
    Start-Sleep -Seconds 2
} else {
    Write-Step "Instalando servicio $ServiceName..."
    $SvcExe = Join-Path $AppDir "lbamonitor-svc.exe"
    & $Nssm install $ServiceName $SvcExe
}

# Configurar servicio
Write-Step "Configurando servicio..."
& $Nssm set $ServiceName Start SERVICE_AUTO_START
& $Nssm set $ServiceName AppDirectory $AppDir
& $Nssm set $ServiceName AppStdout (Join-Path $DataDir "logs\svc-stdout.log")
& $Nssm set $ServiceName AppStderr (Join-Path $DataDir "logs\svc-stderr.log")
& $Nssm set $ServiceName AppRotateFiles 1
& $Nssm set $ServiceName AppRotateBytes 10485760  # 10 MB
& $Nssm set $ServiceName AppRotateBackups 5
& $Nssm set $ServiceName Description "LBAMonitor - Monitoreo de copias a memorias USB/MTP"
& $Nssm set $ServiceName DisplayName "LBAMonitor Service"

# Configurar recuperación automática
& $Nssm set $ServiceName AppRestartDelay 5000  # 5 segundos
& $Nssm set $ServiceName AppExit Default Restart

# Iniciar servicio
Write-Step "Iniciando servicio..."
& $Nssm start $ServiceName
Start-Sleep -Seconds 3

# Verificar
$svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($svc -and $svc.Status -eq "Running") {
    Write-Host ""
    Write-Host "Servicio $ServiceName instalado y arrancado correctamente." -ForegroundColor Green
    Write-Host "  Estado: $($svc.Status)" -ForegroundColor Green
    Write-Host "  Inicio: $($svc.StartType)" -ForegroundColor Green
    Write-Host "  AppDir: $AppDir" -ForegroundColor Gray
    Write-Host "  DataDir: $DataDir" -ForegroundColor Gray
    Write-Host ""
    Write-Host "API disponible en: http://127.0.0.1:8123" -ForegroundColor Cyan
} else {
    Write-Host "Advertencia: el servicio no está en estado Running." -ForegroundColor Yellow
    Write-Host "Revisa los logs en: $DataDir\logs\" -ForegroundColor Yellow
}

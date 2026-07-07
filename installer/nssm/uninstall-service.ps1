# ============================================================
# LBAMonitor — Script para desinstalar el servicio Windows
# ============================================================

param(
    [string]$ServiceName = "LBAMonitorService",
    [string]$AppDir = "C:\Program Files\LBAMonitor"
)

$ErrorActionPreference = "Stop"

function Test-Admin {
    $currentUser = [Security.Principal.WindowsPrincipal][Security.Principal]::GetCurrent()
    return $currentUser.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Admin)) {
    Write-Host "Este script requiere permisos de administrador." -ForegroundColor Red
    exit 1
}

$Nssm = Join-Path $AppDir "nssm.exe"
if (-not (Test-Path $Nssm)) {
    $Nssm = Get-Command "nssm.exe" -ErrorAction SilentlyContinue
    if (-not $Nssm) {
        Write-Host "nssm.exe no encontrado." -ForegroundColor Red
        exit 1
    }
    $Nssm = $Nssm.Source
}

Write-Host "[LBAMonitor] Deteniendo servicio $ServiceName..." -ForegroundColor Cyan
& $Nssm stop $ServiceName 2>$null
Start-Sleep -Seconds 2

Write-Host "[LBAMonitor] Eliminando servicio $ServiceName..." -ForegroundColor Cyan
& $Nssm remove $ServiceName confirm

Write-Host "Servicio eliminado." -ForegroundColor Green

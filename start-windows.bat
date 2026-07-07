@echo off
REM ============================================================
REM LBAMonitor - Script de inicio para Windows
REM Ejecuta: crea venv, instala deps, init BD, arranca servicio
REM ============================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ==========================================================
echo   LBAMonitor - Inicio rapido para Windows
echo ==========================================================
echo.

REM Verificar Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no encontrado en PATH.
    echo Instala Python 3.11+ desde https://www.python.org/downloads/
    echo Asegurate de marcar "Add Python to PATH" durante la instalacion.
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version') do set PYVER=%%i
echo [OK] Python %PYVER% detectado
echo.

REM Crear venv si no existe
if not exist ".venv\Scripts\python.exe" (
    echo [PASO 1/4] Creando entorno virtual...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] No se pudo crear el venv
        pause
        exit /b 1
    )
    echo [OK] Entorno virtual creado en .venv\
) else (
    echo [PASO 1/4] Entorno virtual ya existe
)
echo.

REM Activar venv
call .venv\Scripts\activate

REM Instalar deps
echo [PASO 2/4] Instalando dependencias (puede tardar varios minutos)...
pip install -q -e ".\backend[dev]"
if errorlevel 1 (
    echo [ERROR] Fallo la instalacion de dependencias
    pause
    exit /b 1
)
echo [OK] Dependencias instaladas
echo.

REM Inicializar BD
echo [PASO 3/4] Inicializando base de datos...
lbamonitor-cli init-db
if errorlevel 1 (
    echo [ERROR] Fallo la inicializacion de BD
    pause
    exit /b 1
)
echo [OK] Base de datos lista
echo.

REM Arrancar servicio
echo [PASO 4/4] Arrancando servicio LBAMonitor...
echo.
echo ==========================================================
echo   LBAMonitor esta corriendo!
echo ==========================================================
echo.
echo   Web UI:  http://127.0.0.1:8123
echo   API docs: http://127.0.0.1:8123/docs
echo.
echo   Presiona Ctrl+C para detener el servicio.
echo ==========================================================
echo.

lbamonitor-svc

pause

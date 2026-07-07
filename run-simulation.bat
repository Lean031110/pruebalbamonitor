@echo off
REM ============================================================
REM LBAMonitor - Ejecutar simulacion E2E completa
REM ============================================================

cd /d "%~dp0"
if not exist ".venv\Scripts\activate.bat" (
    echo [ERROR] Venv no encontrado. Ejecuta start-windows.bat primero.
    pause
    exit /b 1
)

call .venv\Scripts\activate
cd backend
python scripts\simulate_full_flow.py

echo.
echo Presiona una tecla para salir...
pause >nul

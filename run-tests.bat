@echo off
REM ============================================================
REM LBAMonitor - Ejecutar tests
REM ============================================================

cd /d "%~dp0"
if not exist ".venv\Scripts\activate.bat" (
    echo [ERROR] Venv no encontrado. Ejecuta start-windows.bat primero.
    pause
    exit /b 1
)

call .venv\Scripts\activate
cd backend
python -m pytest tests/ -v --no-cov

echo.
echo Presiona una tecla para salir...
pause >nul

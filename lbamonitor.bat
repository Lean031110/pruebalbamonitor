@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

:MENU
cls
echo.
echo ==========================================================
echo   LBAMonitor v4.0.0 - Menu Principal
echo ==========================================================
echo.
echo   1.  Instalar todo (deps + BD + frontend)
echo   2.  Iniciar servicio (backend + API)
echo   3.  Detener servicio
echo   4.  Iniciar Desktop App (PySide6)
echo   5.  Iniciar modo Kiosco
echo   6.  Ejecutar tests
echo   7.  Ejecutar simulacion E2E
echo   8.  Compilar .exe (PyInstaller)
echo   9.  Inicializar BD
echo   10. Reset BD (eliminar y recrear)
echo   11. Backup ahora
echo   12. Ver logs
echo   13. Generador de licencias (GUI)
echo   14. Web Flask (catalogo + stats)
echo   15. Salir
echo.
echo ==========================================================
set /p choice="Selecciona una opcion (1-15): "

if "%choice%"=="1" goto INSTALL
if "%choice%"=="2" goto START
if "%choice%"=="3" goto STOP
if "%choice%"=="4" goto DESKTOP
if "%choice%"=="5" goto KIOSK
if "%choice%"=="6" goto TEST
if "%choice%"=="7" goto SIMULATE
if "%choice%"=="8" goto BUILD
if "%choice%"=="9" goto DBINIT
if "%choice%"=="10" goto DBRESET
if "%choice%"=="11" goto BACKUP
if "%choice%"=="12" goto LOGS
if "%choice%"=="13" goto LICENSE
if "%choice%"=="14" goto WEB
if "%choice%"=="15" goto EXIT
goto MENU

:INSTALL
echo [LBAMonitor] Instalando todo...
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
)
call .venv\Scripts\activate
python -m pip install --upgrade pip --quiet
pip install --default-timeout=100 --no-cache-dir -e ".\backend"
pip install --default-timeout=100 --no-cache-dir PySide6 pystray pillow websockets flask
if exist "backend\requirements.txt" pip install --default-timeout=100 --no-cache-dir -r backend\requirements.txt
cd frontend && npm install --no-fund --no-audit && npm run build && cd ..
if exist "C:\ProgramData\LBAMonitor\data\lbamonitor.db" (
    del /q "C:\ProgramData\LBAMonitor\data\lbamonitor.db" 2>nul
    del /q "C:\ProgramData\LBAMonitor\data\lbamonitor.db-wal" 2>nul
    del /q "C:\ProgramData\LBAMonitor\data\lbamonitor.db-shm" 2>nul
)
lbamonitor-cli init-db --reset
echo.
echo [OK] Instalacion completada!
echo   Usuario: admin
echo   Password: admin123
echo.
pause
goto MENU

:START
echo [LBAMonitor] Iniciando servicio...
call .venv\Scripts\activate
lbamonitor-svc
pause
goto MENU

:STOP
echo [LBAMonitor] Deteniendo servicio...
taskkill /f /im lbamonitor-svc.exe 2>nul
for /f "tokens=2" %%i in ('tasklist /fi "imagename eq python.exe" /fo list ^| findstr "PID"') do (
    wmic process where "ProcessId=%%i" get CommandLine 2>nul | findstr "lbamonitor" >nul && taskkill /f /pid %%i 2>nul
)
echo [OK] Servicio detenido
pause
goto MENU

:DESKTOP
echo [LBAMonitor] Iniciando Desktop App (PySide6)...
call .venv\Scripts\activate
python -m desktop_qt
pause
goto MENU

:KIOSK
echo [LBAMonitor] Iniciando modo Kiosco...
call .venv\Scripts\activate
python -m desktop_qt --kiosk
pause
goto MENU

:TEST
echo [LBAMonitor] Ejecutando tests...
call .venv\Scripts\activate
cd backend && python -m pytest tests/ -v --no-cov && cd ..
pause
goto MENU

:SIMULATE
echo [LBAMonitor] Ejecutando simulacion E2E...
call .venv\Scripts\activate
python backend\scripts\simulate_full_flow.py
pause
goto MENU

:BUILD
echo [LBAMonitor] Compilando .exe...
call .venv\Scripts\activate
pip install pyinstaller --quiet
pyinstaller installer\pyinstaller\svc.spec --noconfirm
echo [OK] Build en installer\build\
pause
goto MENU

:DBINIT
echo [LBAMonitor] Inicializando BD...
call .venv\Scripts\activate
lbamonitor-cli init-db --reset
pause
goto MENU

:DBRESET
echo [LBAMonitor] ATENCION: Esto eliminara todos los datos.
set /p confirm="Escribe SI para confirmar: "
if not "%confirm%"=="SI" goto MENU
del /q "C:\ProgramData\LBAMonitor\data\lbamonitor.db*" 2>nul
call .venv\Scripts\activate
lbamonitor-cli init-db --reset
echo [OK] BD recreada
pause
goto MENU

:BACKUP
echo [LBAMonitor] Forzando backup...
call .venv\Scripts\activate
python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8123/api/backups/trigger', method='POST', timeout=30)"
echo [OK] Backup creado
pause
goto MENU

:LOGS
echo [LBAMonitor] Ultimos 50 logs:
type "C:\ProgramData\LBAMonitor\logs\lbamonitor.log" 2>nul | findstr /n "." | findstr "^[0-9]*:" > %temp%\lba_logs.txt
for /f "tokens=1,* delims=:" %%a in (%temp%\lba_logs.txt) do set last=%%a
set /a start=last-50
if %start% lss 1 set start=1
for /f "tokens=1,* delims=:" %%a in (%temp%\lba_logs.txt) do if %%a geq %start% echo %%b
pause
goto MENU

:LICENSE
echo [LBAMonitor] Abriendo generador de licencias...
call .venv\Scripts\activate
python tools\license_generator\license_generator.py
pause
goto MENU

:WEB
echo [LBAMonitor] Iniciando Web Flask (catalogo + stats)...
call .venv\Scripts\activate
python -c "from web.app import run_web; run_web(port=5000)"
pause
goto MENU

:EXIT
exit /b 0

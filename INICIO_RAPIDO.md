# LBAMonitor v4.0.0 — Guía de Inicio Rápido

> **Desktop PySide6** = interfaz principal · **Web Flask** = catálogo + estadísticas

---

## 🚀 3 pasos

### Paso 1: Instalar
```bat
lbamonitor.bat
:: Escribe 1 y Enter (Instalar todo)
```
Esto instala: Python deps + PySide6 + Flask + compila frontend + crea BD + usuario admin

### Paso 2: Iniciar servicio
```bat
lbamonitor.bat
:: Escribe 2 y Enter (Iniciar servicio)
```
El servicio corre en http://127.0.0.1:8123

### Paso 3: Abrir Desktop App
```bat
lbamonitor.bat
:: Escribe 4 y Enter (Desktop PySide6)
```
- La app arranca el servicio automáticamente si no está corriendo
- Login: `admin` / `admin123`
- Para kiosco: opción 5

---

## 📱 Menú del script maestro

```
 1.  Instalar todo
 2.  Iniciar servicio
 3.  Detener servicio
 4.  Iniciar Desktop (PySide6)
 5.  Iniciar Kiosco
 6.  Tests
 7.  Simulación E2E
 8.  Compilar .exe
 9.  Inicializar BD
 10. Reset BD
 11. Backup ahora
 12. Ver logs
 13. Generador de licencias
 14. Web Flask
 15. Salir
```

---

## 🌐 Web Flask

```bat
lbamonitor.bat
:: Escribe 14 y Enter
```
- **Catálogo público**: http://127.0.0.1:5000 (sin login)
- **Estadísticas**: http://127.0.0.1:5000/stats (login admin)
- **Cierres**: http://127.0.0.1:5000/closures (login admin)

---

## 🔐 Credenciales

- Usuario: `admin`
- Password: `admin123`
- Cambiar después del primer login

---

## 🔧 Troubleshooting

### El servicio no arranca
1. Borrar BD: opción 10 (Reset BD)
2. Opción 9 (Inicializar BD)
3. Opción 2 (Iniciar servicio)

### PySide6 no abre
```bat
pip install PySide6
```

### No detecta USBs
- El monitor usa WM_DEVICECHANGE (ventana oculta) + polling cada 5s
- Verifica logs: opción 12
- Debes ver "WM_DEVICECHANGE: USB insertada: E:"

### MediaDevices.dll no encontrada
- La DLL está en `backend/lib/MediaDevices.dll`
- El desktop la copia a `C:\ProgramData\LBAMonitor\lib\` automáticamente
- Si falta, MTP usa fallback PowerShell (Get-PnpDevice)

---

## 📚 Más documentación

- [docs/TECHNICAL_REFERENCE.md](docs/TECHNICAL_REFERENCE.md) — referencia técnica completa
- [docs/MIRON-analysis.md](docs/MIRON-analysis.md) — análisis de MIRON
- [docs/plugins.md](docs/plugins.md) — guía de plugins
- [CHANGELOG.md](CHANGELOG.md) — historial de versiones

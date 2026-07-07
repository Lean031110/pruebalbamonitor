# LBAMonitor — Documentación Técnica Completa

> **Versión**: 4.0.0 · **Fecha**: 2026-07-06 · **Idioma**: Español
>
> Documentación técnica de referencia para desarrolladores, contribuyentes y administradores.

---

## Tabla de contenidos

1. [Resumen ejecutivo](#1-resumen-ejecutivo)
2. [Historia y evolución](#2-historia-y-evolución)
3. [Arquitectura general](#3-arquitectura-general)
4. [Modelo de datos](#4-modelo-de-datos)
5. [Backend — Monitoreo USB/MTP](#5-backend--monitoreo-usbmtp)
6. [Backend — API REST + WebSocket](#6-backend--api-rest--websocket)
7. [Desktop App — PySide6](#7-desktop-app--pyside6)
8. [Web App — Flask](#8-web-app--flask)
9. [Sistema de licencias](#9-sistema-de-licencias)
10. [Sistema de plugins](#10-sistema-de-plugins)
11. [Seguridad](#11-seguridad)
12. [Empaquetado y despliegue](#12-empaquetado-y-despliegue)
13. [Logging y observabilidad](#13-logging-y-observabilidad)
14. [Comparativa con MIRON](#14-comparativa-con-miron)

---

## 1. Resumen ejecutivo

LBAMonitor es un sistema de monitoreo de copias a memorias USB/MTP para Windows, diseñado para copisterías y kioscos. Reemplaza al software cubano **Uatcher** (alias **MIRON**, autor MIRON © 2022) con una arquitectura moderna de 3 componentes:

| Componente | Tecnología | Rol |
|---|---|---|
| Backend (servicio) | Python + FastAPI + SQLAlchemy | Monitoreo USB/MTP, BD, API REST, WebSocket |
| Desktop App | PySide6 (Qt6) | Interfaz PRINCIPAL: cobros, monitoreo, configuración, bandeja |
| Web App | Flask + HTML puro | Catálogo público + estadísticas + cierres de caja |

**Versión actual**: 4.0.0 — reestructuración con PySide6 nativo, Flask web, DeviceChangeListener WM_DEVICECHANGE.

---

## 2. Historia y evolución

### Uatcher (MIRON) — Software original
- **Autor**: MIRON, © 2022
- **Stack**: C# / .NET Framework 4.5, WinForms, Entity Framework 6, SQL Server Compact 4
- **Componentes**: `Uatcher.Service.exe` (Topshelf), `Uatcher.UI.exe` (WinForms), `Uatcher.EF.dll`, `Uatcher.Common.dll`
- **Ofuscación**: Dotfuscator Professional (evaluación)
- **Descripción**: "Aplicación para monitorear copias a memorias en Cuba"
- **Limitaciones**: sin API REST, sin acceso remoto, SQLCE deprecated, sin auth, sin plugins

### LBAMonitor — Reimplementación
- **v1.0.0** (2026-07-05): Paridad funcional con Uatcher + auth JWT + API REST + web React
- **v2.0.0**: Correcciones críticas (MTP pythonnet, identificación USB compuesta, alembic auto-upgrade)
- **v3.0.0**: Popup cobro forzado, generador licencias GUI, requirements.txt fijas, script maestro
- **v3.1.0**: DeviceChangeListener WM_DEVICECHANGE, filtro DRIVE_REMOVABLE, plugins, MediaDevices.dll, log_manager
- **v4.0.0** (actual): PySide6 nativo (reemplaza PyWebView), Flask web (reemplaza React/Node), logo profesional

---

## 3. Arquitectura general

```
┌─────────────────────────────────────────────────────────────┐
│                     Windows Host                             │
│                                                              │
│  ┌──────────────────────┐    ┌───────────────────────────┐  │
│  │  lbamonitor-svc      │    │  Desktop App (PySide6)    │  │
│  │  (Backend Python)    │    │  Interfaz PRINCIPAL       │  │
│  │                      │    │                           │  │
│  │  - FastAPI REST      │◀───│  - Login JWT              │  │
│  │  - WebSocket /ws     │    │  - Dashboard KPIs         │  │
│  │  - SQLAlchemy async  │    │  - USBs + cobro + popup   │  │
│  │  - SQLite WAL        │    │  - Clientes/VIP           │  │
│  │  - DeviceChange WM   │    │  - Catálogo               │  │
│  │  - MTP (pythonnet)   │    │  - Configuración          │  │
│  │  - Watchdog          │    │  - Bandeja sistema        │  │
│  │  - Plugins           │    │  - Kiosco                 │  │
│  │  - ClockMonitor      │    │  - WebSocket events       │  │
│  └──────────┬───────────┘    └───────────────────────────┘  │
│             │                                                │
│             ▼                                                │
│  ┌──────────────────────┐                                    │
│  │  Web Flask           │  ← http://IP:5000                 │
│  │  - Catálogo público  │    (sin login)                    │
│  │  - Estadísticas día  │    (login admin)                  │
│  │  - Cierres de caja   │                                    │
│  └──────────────────────┘                                    │
└──────────────────────────────────────────────────────────────┘
```

### Flujo de datos principal

```
[USB conectada]
    │
    ├── WM_DEVICECHANGE (kernel → ventana oculta)
    │   └── DeviceChangeListener._wnd_proc()
    │       └── _is_removable_drive() filtro
    │           └── _on_device_inserted_sync(drive_letter)
    │               └── get_usb_info() → USBDeviceInfo
    │                   └── asyncio.run_coroutine_threadsafe(_handle_usb_insertion)
    │                       ├── USBDevice.get_or_create(fingerprint)
    │                       ├── compute_history(prev_count, prev_sum)
    │                       ├── InsertedDrive.create()
    │                       ├── CopyMonitor.start(watchdog)
    │                       └── PluginManager.dispatch("on_usb_inserted")
    │
[Archivo copiado a USB]
    │
    └── CopyMonitor (watchdog FileSystemEventHandler)
        └── _DebouncedHandler.on_created()
            └── categorize_file() → FileCategory
                └── CopyRepository.create()

[USB extraída sin pago]
    │
    └── _handle_usb_removal()
        └── if payment is None:
            └── EventBus.publish("drive.eject.pending")
                └── Desktop WebSocket listener
                    └── CheckoutPopup (Qt nativo)
                        └── PATCH /payment + POST /eject
```

---

## 4. Modelo de datos

### 28 tablas SQLAlchemy 2.0

**Tablas de Uatcher (paridad funcional):**

| Tabla | Propósito | Campos clave |
|---|---|---|
| `users` | Operadores con roles | id, username, password_hash (PBKDF2), role, active |
| `inserted_drives` | Cada inserción de USB | id, insertion_date_time, name, serial_number, payment, comment, comment_fixed, row_color, user_id, removed_drive_id |
| `removed_drives` | Cada extracción | id, removal_date_time, name |
| `copies` | Archivos copiados | id, copy_date_time, full_path, extension, file_name, size_bytes, category |
| `deletions` | Archivos borrados | id, deletion_date_time, full_path, file_name |
| `payment_alterations` | Trazabilidad de cambios de pago | id, previous_payment, new_payment, alteration_date_time, user_id |
| `pc_datetime_changes` | Cambios de reloj detectados | id, moment, to |
| `service_sessions` | Sesiones del servicio | id, start_date_time, end_date_time, alive_date_time, session_time |
| `key_values` | Settings genéricas (paridad Uatcher) | id, key, value |

**Tablas nuevas de LBAMonitor:**

| Tabla | Propósito |
|---|---|
| `usb_devices` | Registro único por fingerprint (SHA-256 DeviceID + VolumeSerial) |
| `usb_sessions` | Sesión detallada con stats (files_copied, bytes_copied, avg_speed) |
| `file_operations` | Evento unificado (created/modified/deleted/renamed) |
| `billings` | Cobro con PricingEngine (suggested, charged, discounts, tax) |
| `clients` | Cliente asociado a USB (1:1, con puntos y tier) |
| `vip_entries` | Tipo VIP (NONE/VIP/BLOCKED/NEVER_PAYS/FREE/DISCOUNT/EMPLOYEE/BUSINESS) |
| `membership_levels` | 5 niveles Bronce→Diamante con umbrales y descuentos |
| `rewards` | Recompensas otorgadas (6 tipos) |
| `catalog_entries` | Catálogo multimedia (movie/series/music/document/game/app) |
| `catalog_sources` | Discos indexados automáticamente |
| `configuration` | Settings tipadas (section+key+value_type) |
| `activity_logs` | Auditoría de acciones administrativas |
| `error_logs` | Errores del sistema |
| `backup_records` | Historial de backups |
| `notifications` | Notificaciones UI |
| `report_records` | Historial de reportes generados |
| `daily_closures` | Cierres de caja diarios con métricas consolidadas |
| `price_history` | Historial de cambios de tarifas |
| `price_rules` | Reglas de precios por contexto (folder/capacity/fixed/discount) |

### Decisiones de diseño
- **Todas las timestamps en UTC** (`DateTime(timezone=True)` + `default=utcnow`)
- **Fingerprint USB compuesto**: `SHA-256(DeviceID + VolumeSerialNumber)` — sobrevive formateos
- **Soft deletes**: `active=False` en usuarios y catálogo
- **WAL mode**: `PRAGMA journal_mode=WAL` + `synchronous=NORMAL` + `cache_size=64MB`

---

## 5. Backend — Monitoreo USB/MTP

### 5.1 DeviceChangeListener (PRIMARIO — WM_DEVICECHANGE)

**Método**: Ventana oculta Win32 que recibe `WM_DEVICECHANGE` (0x0219) del kernel.

**Flujo**:
1. `win32gui.RegisterClass()` registra clase de ventana
2. `win32gui.CreateWindow()` crea ventana oculta (sin GUI)
3. `PumpWaitingMessages()` + `time.sleep(0.05)` = bucle de mensajes (20fps, bajo CPU)
4. `_wnd_proc()` procesa `DBT_DEVICEARRIVAL` / `DBT_DEVICEREMOVECOMPLETE`
5. `_get_drive_letters()` parsea `DEV_BROADCAST_VOLUME` del `lparam`
6. `_is_removable_drive()` filtra con `win32api.GetDriveType()` — solo `DRIVE_REMOVABLE` y `DRIVE_FIXED`
7. Callbacks síncronos → `asyncio.run_coroutine_threadsafe()` al event loop principal

**Ventajas sobre WMI events**:
- 100% confiable (kernel directo, no servicio WMI)
- Latencia < 100ms
- Cero CPU cuando no hay eventos
- Sin errores COM (-2147217406)

### 5.2 USBMonitor (FALLBACK — polling)

**Método**: `win32api.GetLogicalDrives()` + `win32file.GetDriveType()` cada 5 segundos.

Se activa solo si `DeviceChangeListener` falla. Compara set de drives conocidas vs actuales para detectar inserciones/extracciones.

### 5.3 MTPMonitor (celulares Android)

**Detección**: 2 capas con fallback:
1. **Primario**: `pythonnet` + `MediaDevices.dll` — busca DLL en 4 rutas (`_MEIPASS`, `backend/lib/`, `Program Files/LBAMonitor/lib/`, `ProgramData/LBAMonitor/lib/`)
2. **Fallback**: PowerShell `Get-PnpDevice -Class WPD` — sin DLL, solo PowerShell

**Polling**: cada 3 segundos (MTP no soporta eventos nativos).

### 5.4 CopyMonitor (watchdog)

**Método**: `watchdog.Observer` con `FileSystemEventHandler` personalizado.

- **Debouncer 500ms**: filtra eventos duplicados (Created+Modified+Modified)
- **Categorización**: `categorize_file()` por extensión → FileCategory (video/movie/series/music/document/image/game/app)
- **Distinción película/serie**: regex (`S01E05`, `1x05`, "Temporada 1" → series; `1080p`, `(2024)` → movie)
- **Exclusión**: Thumbs.db, .DS_Store, desktop.ini, ~$*, *.tmp
- **Stats en vivo**: files_copied, bytes_copied, operation_count, category_counts

### 5.5 ClockMonitor

Cada 60s compara UTC actual vs anterior. Si delta > 120s, registra `PCDatetimeChange`.
Threshold subido a 120s (antes 60s) para evitar falsos positivos por latencia normal.

### 5.6 SessionHeartbeat

Crea `ServiceSession` al arrancar, actualiza `AliveDateTime` cada 5 min, cierra con `EndDateTime` + `SessionTime` al detener.

### 5.7 PluginManager

Carga plugins `.py` desde `ProgramData/LBAMonitor/plugins/` y `backend/plugins/`.
9 eventos: `on_usb_inserted`, `on_usb_removed`, `on_file_copied`, `on_file_deleted`, `on_payment_registered`, `on_session_started`, `on_session_ended`, `on_backup_created`, `on_license_activated`.
Dispatch síncrono, errores aislados por plugin.

---

## 6. Backend — API REST + WebSocket

### 6.1 FastAPI

- **90+ endpoints** en 20 routers
- **OpenAPI 3.1** autogenerado en `/docs` (Swagger) y `/redoc`
- **Paginación**: `?page=1&page_size=50` (max 500)
- **Errores**: RFC 7807 Problem Details
- **Métricas Prometheus** en `/metrics`

### 6.2 Routers principales

| Router | Endpoints | Función |
|---|---|---|
| `/api/health` | 3 | Salud + ping + disco |
| `/api/auth` | 4 | Login + me + refresh + logout |
| `/api/users` | 5 | CRUD operadores |
| `/api/inserted-drives` | 10 | Listado + filtros + cobro + eject + factura + webcam |
| `/api/copies` | 5 | Listado + agregados (by_ext, by_day, by_hour, top_files) |
| `/api/statistics` | 10 | KPIs + series + rankings + insights |
| `/api/billings` | 6 | Cobros + patrones + calculate + preview |
| `/api/catalog` | 6 | CRUD + top_copied |
| `/api/clients` | 4 | CRUD |
| `/api/memberships` | 4 | Niveles + distribución + recompute |
| `/api/rewards` | 3 | Listar + crear + aplicar |
| `/api/settings` | 12 | BusinessInfo + PublicityFolder + VideoFolders + etc. |
| `/api/license` | 3 | Estado + machine-id + activate |
| `/api/sessions` | 2 | Listado + current |
| `/api/backups` | 3 | Listado + trigger + download |
| `/api/closures` | 4 | Cierres de caja CRUD |
| `/api/admin` | 5 | Status + plugins + logs/tail + service start/stop |
| `/api/web` | 4 | Stats daily/monthly + closures + catalog público |
| `/api/price-rules` | 5 | CRUD reglas + seed defaults |
| `/api/advanced` | 4 | Pricing history + catalog import + catalog scan + event replay |
| `WS /ws/events` | 1 | WebSocket eventos en tiempo real |

### 6.3 WebSocket /ws/events

Eventos publicados por el `EventBus`:
- `drive.inserted`, `drive.removed`, `drive.eject.pending`
- `file.copied`, `file.deleted`
- `payment.altered`, `billing.registered`
- `service.session.started`, `service.session.ended`
- `pc.datetime.changed`
- `reward.granted`, `membership.upgraded`
- `log.entry` (v3.1.0 — logs en tiempo real)

**Buffer circular**: últimos 200 eventos para replay vía `GET /api/admin/event-replay`.

### 6.4 PricingEngine

5 modos: `per_gb`, `per_mb`, `per_file`, `fixed`, `custom`.
Descuentos encadenados: VIP (0-100%) + membresía (0-20%) + promoción (0-N%).
Límites min_price/max_price.

### 6.5 Migraciones Alembic

- **Auto-upgrade** en `_bootstrap_sync()` ANTES de `uvicorn.run()` (síncrono, crítico)
- Si la BD ya tiene tablas pero no `alembic_version` → `alembic stamp head` automático
- 2 migraciones: `0001_initial_schema` + `0002_add_closures_pricehistory_catalogsources_pricerules`

---

## 7. Desktop App — PySide6

### 7.1 Estructura

```
desktop_qt/
├── main.py              # Entrypoint: login + ventana principal + auto-arranque servicio
├── api/
│   └── client.py        # ApiClient singleton con JWT
├── ui/
│   ├── main_window.py   # QMainWindow: sidebar + 8 tabs + bandeja + WS
│   ├── login_dialog.py  # QDialog login (usuario/password)
│   ├── dashboard_tab.py # KPIs del día (refrescados vía WS)
│   ├── usb_tab.py       # USBs activos + cobro + comentario + color
│   ├── checkout_popup.py# Popup cobro forzado Qt nativo (no Tkinter)
│   ├── billing_tab.py   # Tabla cobros
│   ├── clients_tab.py   # Clientes + membresías
│   ├── catalog_tab.py   # Catálogo CRUD
│   ├── settings_tab.py  # Configuración
│   ├── logs_tab.py      # Visor logs
│   └── license_tab.py   # Licencia + activación
├── assets/
│   └── style.qss        # Tema oscuro profesional (estilo MIRON mejorado)
└── requirements.txt     # PySide6
```

### 7.2 Flujo de arranque

1. `ensure_service_running()` — verifica API, arranca `lbamonitor-svc` si no responde
2. `QApplication` + carga `style.qss`
3. `LoginDialog.login()` — POST `/api/auth/login`, guarda JWT
4. `MainWindow` con sidebar + QStackedWidget (8 tabs)
5. `QSystemTrayIcon` con menú (Mostrar, Backup, Salir)
6. `QTimer` 5s — refresca tab actual
7. `QTimer` 30s — verifica salud del servicio
8. Thread WebSocket — escucha `/ws/events` para eventos en tiempo real
9. Señales Qt (`SignalsBridge`) — marshalling cross-thread para UI

### 7.3 Popup de cobro forzado (Qt nativo)

- Se dispara con evento `drive.eject.pending` del WebSocket
- `QDialog` con `Qt.WindowStaysOnTopHint` — siempre encima
- Sin botón cerrar (X) — solo "COBRAR Y EXPULSAR"
- Botones rápidos: 25, 50, 100, 200, 500 CUP
- Enter = cobrar
- Al cobrar: `PATCH /payment` + `POST /eject`

### 7.4 Modo Kiosco

`python -m desktop_qt --kiosk` → `showFullScreen()` + `FramelessWindowHint`.

---

## 8. Web App — Flask

### 8.1 Rutas

| Ruta | Auth | Función |
|---|---|---|
| `/` | No | Catálogo público con buscador + filtros |
| `/login` | No | Login admin |
| `/stats` | Sí | KPIs del día + insights (auto-refresh 30s) |
| `/closures` | Sí | Cierres de caja históricos |
| `/logout` | — | Cierra sesión |

### 8.2 Stack

- Flask (sin Node.js, sin React)
- Jinja2 templates con tema oscuro CSS
- `urllib.request` para llamar al backend FastAPI
- Sesión Flask para JWT

---

## 9. Sistema de licencias

### 9.1 Machine ID (HWID)

`SHA-256` de:
- `Win32_Processor.ProcessorId`
- `Win32_BIOS.SerialNumber`
- `Win32_BaseBoard.SerialNumber`
- `Win32_ComputerSystemProduct.UUID`

Tolerancia: 1 componente puede cambiar sin invalidar.
Fallback para PCs clónicas ("To be filled by O.E.M.").

### 9.2 Licencia HMAC-SHA256

- **100% offline** (sin activación online, Cuba-friendly)
- Payload: `{hwid, tier, issued_at, expires, business}`
- Firma: `HMAC-SHA256(secret, base64url(payload))`
- Distribución: `lbamonitor-cli generate-license` o GUI `tools/license_generator/`
- Verificación: `verify_license(license_str, machine_id, secret)`
- SECRET_KEY debe coincidir entre backend y generador

### 9.3 Generador GUI

`tools/license_generator/license_generator.py` — app tkinter standalone:
- Campos: Machine ID, nombre negocio, tier, días validez
- Botones: Generar, Copiar, Guardar archivo, Verificar
- Compilable a .exe con `build_license_generator.bat`

---

## 10. Sistema de plugins

Ver `docs/plugins.md` para guía completa.

### Eventos (9)
`on_usb_inserted`, `on_usb_removed`, `on_file_copied`, `on_file_deleted`, `on_payment_registered`, `on_session_started`, `on_session_ended`, `on_backup_created`, `on_license_activated`

### Ubicaciones
1. `C:\ProgramData\LBAMonitor\plugins\` (producción)
2. `backend/plugins/` (desarrollo)

### API
- `GET /api/admin/plugins` — listar
- `POST /api/admin/plugins/reload` — recargar sin reiniciar

---

## 11. Seguridad

### 11.1 Autenticación
- **JWT** con expiración 24h (1440 min)
- **Login obligatorio** por defecto (`require_auth = true`)
- **PBKDF2-HMAC-SHA256** 200k iteraciones para passwords
- **3 roles**: admin, manager, operator
- **Protección último admin**: no se puede eliminar/desactivar el último admin activo

### 11.2 Middleware
- CORS estricto (solo orígenes configurados)
- Rate limiting (pendiente v4.1)
- Read-only mode automático si disco < 500MB
- `bandit` + `safety` en CI/CD

### 11.3 BD
- `icacls /grant Todos:(OI)(CI)F` automático en `init_engine_sync()`
- PRAGMA `foreign_keys=ON`
- VACUUM INTO para backups consistentes

---

## 12. Empaquetado y despliegue

### 12.1 PyInstaller
- 3 specs: `svc.spec` (servicio), `desktop.spec` (PyWebView legacy), `cli.spec`
- `--onedir` + UPX (no `--onefile` — mejor reputación AV)
- Excluye matplotlib, tkinter, tests
- Incluye `MediaDevices.dll` en `lib/`
- Icono: `assets/icon.ico`

### 12.2 Inno Setup
- Instalador MSI con registro de servicio NSSM
- Creación de directorios en ProgramData
- Upgrade-aware (detiene servicio previo)
- Desinstalación limpia (conserva datos)

### 12.3 NSSM
- Servicio Windows auto-start
- Rotación de logs (10 MB, 5 archivos)
- Recuperación automática en crash (restart 5s)

### 12.4 Script maestro
`lbamonitor.bat` — menú interactivo con 15 opciones (1-15).

---

## 13. Logging y observabilidad

### 13.1 LogManager

- **loguru** con 4 sinks: consola, archivo diario, archivo por tamaño (10MB), errores
- **Rotación**: diaria + 10 MB + compresión `.gz`
- **Buffer circular**: últimos 500 logs en memoria
- **WebSocket**: logs broadcast en tiempo real vía `log.entry` events
- **Endpoint**: `GET /api/admin/logs/tail?lines=100`

### 13.2 Prometheus
`prometheus-fastapi-instrumentator` expone `/metrics` para scraping con Grafana.

### 13.3 Healthcheck
`GET /api/health` — versión, plataforma, config, counts, session, `db_integrity` (PRAGMA integrity_check), `device_listener_active`.

---

## 14. Comparativa con MIRON

| Característica | MIRON (Uatcher) | LBAMonitor v4 |
|---|---|---|
| Lenguaje | C#/.NET 4.5 | Python 3.11+ |
| UI Desktop | WinForms | **PySide6 (Qt6)** |
| Detección USB | WM_DEVICECHANGE | **WM_DEVICECHANGE** (mismo método) |
| Filtro removibles | Sí | Sí (DRIVE_REMOVABLE + DRIVE_FIXED) |
| MTP (celulares) | MediaDevices.dll | MediaDevices.dll + PowerShell fallback |
| Polling MTP | ? | 3 segundos |
| Polling USB fallback | No | Sí (5s, solo si WM_DEVICECHANGE falla) |
| Plugins | No | **Sí (9 eventos)** |
| Popup cobro forzado | No | **Sí (Qt nativo)** |
| Login | No | **JWT con roles** |
| API REST | No | **FastAPI + OpenAPI (90+ endpoints)** |
| WebSocket | No | **Sí (11 tipos de eventos)** |
| Web | No | **Flask (catálogo + stats)** |
| Kiosco | No | **Sí** |
| Estadísticas | Básicas | **Completas + gráficos + insights** |
| Membresías | No | **5 niveles + 6 reglas recompensas** |
| Catálogo | Sí | **Sí + import CSV + escaneo discos** |
| Backup | No | **VACUUM INTO + red local SMB** |
| Licencia | Propietario | **HMAC offline + GUI generador** |
| Cobro por USB | Sí | **Sí + popup forzado + colores + comentarios** |
| Comentarios USB | Sí | **Sí (libre + fijo)** |
| Historial | Sí | **Sí + filtros avanzados** |
| BD | SQLCE 4 (deprecated) | **SQLite WAL / PostgreSQL** |
| Migraciones | migrate.exe externo | **Alembic auto-upgrade** |
| Código | Cerrado (Dotfuscator) | **Abierto** |
| Logo | Sí | **Sí (SVG profesional)** |
| Script maestro | No | **Sí (menú 15 opciones)** |
| Tests | No | **103 pytest + 16 E2E** |
| CI/CD | No | **GitHub Actions (lint + tests + bandit + safety)** |
| Métricas | No | **Prometheus /metrics** |
| Alerta disco lleno | No | **Sí (warning <1GB, read-only <500MB)** |
| Cierre de caja | No | **Sí (con historial + export)** |
| Historial precios | No | **Sí (PriceHistory)** |
| Reglas de precio | No | **Sí (folder/capacity/fixed/discount)** |
| Importación catálogo | No | **Sí (CSV/Excel)** |
| Indexación discos | No | **Sí (escaneo recursivo)** |
| Atajos teclado | No | **Sí (F2, F5, Ctrl+Enter, ?)** |

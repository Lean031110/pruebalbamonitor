# LBAMonitor — Investigación de mercado y tecnológica

> Informe completo generado a partir de búsqueda web exhaustiva (16+ consultas temáticas) y análisis del proyecto LBA USB Manager v3.0 decompilado.
>
> Fecha: 2026-07-05

---

## 1. Uatcher / MIRON — Software cubano de monitoreo de copias a USB

### 1.1. Hallazgos

El nombre "Uatcher" no aparece públicamente en internet. Es probable que sea un nombre interno o un dato mal recordado. El software público que coincide 100% con la descripción es **MIRON**:

- Sitio: https://www.mironcuba.com (hosted como Google Docs viewer)
- App Android: `com.itego.MironApp` en Google Play (paquete pertenece a "itego")
- Descripción: *"MIRON es el programa para los negocios en Cuba que copian Novelas, Series, Películas. Para que puedan saber todo lo que se copió durante el día."*
- Subdominio `palmira.mironcuba.com` = "Catálogo de Audiovisuales — Películas Series Novelas"
- La app Android permite "escanear código QR de cada máquina y actualizar estados de las mismas" → **multi-puesto** con QR

### 1.2. Funcionalidades típicas de software cubano de copias

1. Detección multi-dispositivo: memorias USB, discos externos, **celulares por MTP**
2. Catálogo de audiovisuales navegable (películas/series/novelas)
3. Registro de copias por dispositivo con reporte diario
4. Multi-puesto con QR + app móvil
5. Cobro por GB copiado o por contenido

### 1.3. Otros software cubanos relacionados

| Software | Autor | Función |
|---|---|---|
| PAQUETECOPIES | Roger Peña Sicilia (Cuba rural) | Copiador paralelo a múltiples discos. Portable, <1MB. Modelo: 16 USD/año por recarga saldo. |
| SUPERCOPY | Anónimo (Cuba) | Mencionado en Facebook CUBA PC. Incluye copia a móviles. 582.2 GB. |

### 1.4. Problema real que resuelve

En Cuba el internet es escaso y caro. El **Paquete Semanal** (~1 TB: películas, series, novelas, música, apps, YouTube descargado) se distribuye físicamente por USB/discos. Las "copisterías" o "paqueteros":
- Tienen una PC con varios puertos USB
- Reciben la memoria del cliente y le copian contenido
- **Necesitan cobrar por GB copiado o por contenido**
- Sin software, el dueño no puede saber cuánto se copió a cada USB (los empleados pueden robar copias no facturadas)

MIRON resuelve esto: básicamente un **sistema POS (point-of-sale) para copias a USB**.

### 1.5. Mercado

- Paquete Semanal: 1 TB distribuido cada semana desde ~2008
- Precio copistería: 200-350 CUP por copia completa (2024-25)
- Por GB individual: 0.30-0.50 CUP/GB (paquete), 1-2 CUP/GB (personalizado), 5-10 CUP/GB (software)
- Inversión típica paquetero: ~1000 USD en piezas de PC
- Volumen: un paquetero reporta copiar 80 veces el paquete por semana

### 1.6. Legalidad

Técnicamente ilegal ("producción y circulación informal de publicaciones, grabaciones…") pero tolerada. En 2024 hubo confiscaciones y pánico por Decreto 107, pero el gobierno negó haber prohibido el Paquete. El software debe venderse como "gestión general de copistería", no como "gestión de piratería".

---

## 2. Software similar / competidores

### 2.1. Cibercafé LatAm

| Software | Origen | Modelo | Estado |
|---|---|---|---|
| CiberControl / Control de Ciber | Argentina (CBM) | Servidor + Cliente, control tiempos | Clásico LatAm |
| CyberPlanet | Argentina (TenaxSoft) | Cibercafé + lan center | Comercial activo |
| NetCoffee | Venezuela | Server + Client | Comercial |
| HandyCafe | Turquía | Multilenguaje, billing | Histórico, ahora pago |
| Antamedia Internet Cafe | Serbia | Feature-rich: WiFi, POS, tickets | $149-$799 |
| CyberSquare / CyberCafePro | Brasil | 100% gratis sin ads desde 2022 | Gratis |
| SENET | Polonia | Cloud gaming/esports | SaaS |
| CiberPlex | Perú (open source) | Ventas, cabinas, locutorios | GitHub |
| ALC Lan Manager | Argentina | Lan centers | Comercial |

### 2.2. Software de control USB específico

| Software | Función |
|---|---|
| OsMonitor USB Control | Bloqueo/whitelist USB, solo-lectura, monitoreo |
| USBDLM (Uwe Sieber) | Asignación letras unidad USB, scripts |
| UsbTreeView (Uwe Sieber) | Visor árbol dispositivos USB |

### 2.3. Recomendación

- **No competir con Antamedia/CiberControl** — demasiado grandes y généricos
- El nicho cubano (copisterías Paquete Semanal, MTP, offline, cobro por GB) está **mal cubierto**
- Estudiar MIRON (funcionalidades) y PAQUETECOPIES (modelo de cobro)

---

## 3. Comparativa Python vs Node.js

### 3.1. WMI (Windows Management Instrumentation)

| Aspecto | Python | Node.js |
|---|---|---|
| Librería | `wmi` (wrapper sobre `pywin32`) + `pywin32` directo | `node-wmi` (poco mantenido), o `wmic.exe` via child_process |
| Madurez | Excelente — `pywin32` 4k+ estrellas, Mark Hammond | Pobre — wrappers npm abandonados |
| Acceso Win32_* | Nativo vía COM | Requiere bindings nativos o shell out |

Fuentes: learn.microsoft.com/en-us/answers/questions/1663906 ; pypi.org/project/wmi

### 3.2. Detección de eventos USB

| Mecanismo | Python | Node.js |
|---|---|---|
| WM_DEVICECHANGE | ✅ pywin32 (abdus.dev) | ⚠️ Requiere addon C++ |
| WMI events | ✅ `wmi.WMI().watch_for(notification="DeviceChangeEvent")` | ⚠️ No hay wrapper directo |
| usb-detection (npm) | — | ⚠️ **DEPRECATED** |
| node-usb | — | Mantenido pero orientado a control USB, no detección masiva |

### 3.3. MTP (Windows Portable Devices)

| Lenguaje | Estado |
|---|---|
| **Python** | `comtypes` (mantenido, PyPI 2025) + `Heribert17/mtp` (GitHub, **2025.3.10 mantenido activamente**). Dropbox usa comtypes. |
| **Node.js** | **No hay librería mantenida.** Requeriría addon N-API en C++ o edge-js. |

Fuentes: github.com/Heribert17/mtp ; dropbox.tech/infrastructure/adventures-with-comtypes

> **Decisión clara**: si se necesita MTP (celulares Android), Python gana por paliza.

### 3.4. Servicios Windows

| | Python | Node.js |
|---|---|---|
| Opción 1 | `pywin32` `win32serviceutil.ServiceFramework` (gold standard) | `node-windows` (maduro) |
| Opción 2 | Paquete `windowsservice` PyPI | NSSM (también funciona) |
| Opción 3 | **NSSM** (cualquier .exe) — recomendado | NSSM |

### 3.5. ORM

| Aspecto | SQLAlchemy 2.x | Prisma | TypeORM | Drizzle |
|---|---|---|---|---|
| Madurez | ★★★★★ (desde 2006) | ★★★★ (v7 elimina Rust engine) | ★★★★ (clásico NestJS) | ★★★ |
| Performance | Excelente | Confesadamente **el más lento** | Más rápido que Prisma | Muy rápido |
| SQLite | Excelente | Bien | Bien | Bien |
| Migrations | Alembic (potente) | Prisma Migrate | Manual | Drizzle Kit |

> Para SQLite embebido local con control fino, SQLAlchemy 2.x gana.

### 3.6. Framework HTTP

- FastAPI: ligeramente más rápido que NestJS/Express. Pydantic v2 → validación gratis. OpenAPI autogenerado. Async nativo.
- NestJS: estructurado, TS end-to-end con React.
- Para app local monousuario, la diferencia de throughput es irrelevante.

### 3.7. Empaquetado

| | Python | Node.js |
|---|---|---|
| PyInstaller 6+ | Maduro, onefile/onedir | — |
| Nuitka | Compila a C, mejor startup | — |
| `pkg` | — | **Archivado 2023** |
| `nexe` | — | Activa, menos madura |
| Tamaño | 30-80 MB | 40-150 MB |

### 3.8. Decisión final

> **Python gana por unanimidad técnica para LBAMonitor.**
>
> Node.js obligaría a mantener **dos pilas** (Node para backend + Python para Windows/MTP), duplicando mantenimiento y empaquetado.

---

## 4. Mejores prácticas para detección USB en Windows con Python

### 4.1. Detección de inserción/extracción — 3 enfoques

#### Enfoque A: WM_DEVICECHANGE vía ventana oculta
- Windows emite `WM_DEVICECHANGE` (0x0219) a todas las ventanas
- `wparam`: `DBT_DEVICEARRIVAL` (0x8000), `DBT_DEVICEREMOVECOMPLETE` (0x8004)
- Implementación: `win32gui.RegisterClass` + `CreateWindow` + `PumpMessages`
- Gotcha: servicios LocalSystem **no reciben** WM_DEVICECHANGE (solo ventanas sesión interactiva)

#### Enfoque B: WMI event subscription (RECOMENDADO para servicios)
```python
import wmi
c = wmi.WMI()
watcher = c.Win32_DeviceChangeEvent.watch_for(notification_type="Creation")
```
- Headless-friendly
- Latencia ~1-2s
- WMI es pesado (wmiprvse.exe)

#### Enfoque C: Polling WMI periódico (fallback)
- Cada N segundos: `SELECT * FROM Win32_LogicalDisk WHERE DriveType=2`
- Simple pero ineficiente

### 4.2. Obtener serial number vía WMI

Cadena de asociaciones:
1. `Win32_LogicalDisk` (unidad E:\)
2. → `Win32_LogicalDiskToPartition` →
3. `Win32_DiskPartition`
4. → `Win32_DiskDriveToDiskPartition` →
5. `Win32_DiskDrive` → campo **`SerialNumber`**

Alternativa directa: `Win32_USBControllerDevice` → `Win32_PnPEntity` → `DeviceID` incluye `USB\VID_xxxx&PID_yyyy\SERIAL`.

Librería lista: `usb-monitor` en PyPI ya hace esto.

**Gotchas**:
- USBs baratas pueden reportar serial "0" o vacío → usar VID+PID+InstanceID como fingerprint
- `SerialNumber` puede venir little-endian invertido → normalizar antes de hashear
- USB composite devices (celular con ADB+MTP) → mirar dispositivo padre

### 4.3. WPD (MTP) desde Python

**Mejor opción 2025**: `Heribert17/mtp` (github.com/Heribert17/mtp)
- Versión 2025.3.10 (mantenida este año)
- Usa `comtypes` para COM API de WPD
- Dropbox usa comtypes internamente

Alternativas:
- `python-portable-device` (deffi, GitHub) — menos mantenido
- `py3mtp` / `pymtp` — bindings a libmtp (C library); problemático en Windows

**Gotchas MTP**:
- MTP no expone letras de unidad → archivos se acceden por `objectID` jerárquico
- MTP es lento vs USB mass-storage (~5-20 MB/s Android vs 100+ MB/s pendrive UASP)
- Algunos Android en modo "carga solo" no aparecen como MTP → usuario debe activar "Transferencia de archivos"

### 4.4. FileSystemWatcher: watchdog vs ReadDirectoryChangesW

#### watchdog
- Librería de facto, cross-platform
- Internamente usa `ReadDirectoryChangesW` en Windows
- API: subclass `FileSystemEventHandler`, sobrescribir `on_created/modified/deleted`

#### ReadDirectoryChangesW directo
- Más control pero más código
- Permite ajustar `BUFFER_SIZE` manualmente
- Watchdog tiene issue abierto (#264) para BUFFER_SIZE configurable — hoy hardcoded

### 4.5. Mejores prácticas FileSystemWatcher

#### Buffer overflow
`ReadDirectoryChangesW` devuelve `ERROR_NOTIFY_ENUM_DIR` (1022) cuando el buffer se desborda (típico al copiar Paquete Semanal de 1TB con millones de archivos pequeños).

**Solución**:
- Aumentar `BUFFER_SIZE` (mínimo 64KB, ideal 4MB)
- Si usas watchdog, **no puedes configurarlo hoy** (issue #264)
- **Mejor patrón**: NO observar el filesystem del pendrive; observar el proceso de copia propio

#### Debouncing
Watchdog dispara eventos duplicados: al crear archivo se disparan `Created` + `Modified` + `Modified` + `Modified`.

**Solución**:
- Implementar debouncer: ignorar eventos del mismo path en ventana de N ms (300-500 ms)
- No usar `time.sleep()` en handlers — bloquea el observer. Usar `queue.Queue` + thread consumidor

#### Recomendación técnica LBAMonitor

1. **Detección inserción**: `Win32_DeviceChangeEvent` vía WMI watcher (Enfoque B)
2. **Identificación USB**: cadena `Win32_LogicalDisk → Win32_DiskDrive.SerialNumber`, normalizar little-endian
3. **Identificación MTP**: enumerar vía `Heribert17/mtp` (comtypes+WPD)
4. **Conteo de bytes copiados**: NO usar watchdog del pendrive. Mejor:
   - Si tú controlas la copia: instrumenta `shutil.copy2` con callback
   - Si el usuario copia manualmente: polling de `os.walk()` cada 2s en el destino, diff contra snapshot anterior, sumar `st_size`
5. **Watchdog**: solo para detección de creación de archivos en carpetas locales del PC, con debouncer 500ms

---

## 5. Arquitectura de referencia: servicio + web + desktop

### 5.1. Patrón "local server + web UI + desktop admin"

| Software | Backend | Frontend | Desktop client |
|---|---|---|---|
| Jellyfin | C# .NET (Kestrel) | Web React-ish | Jellyfin Desktop |
| Plex | Node.js + C++ | Web React | Plex Desktop (Electron) |
| Sonarr/Radarr/Lidarr | C# .NET | Web Bootstrap | Solo navegador |
| Home Assistant | Python (asyncio) | Web Components | App oficial (Electron/Capacitor) |
| qBittorrent | C++ + web UI | Web | Solo navegador + GUI nativa |

**Patrón común**:
- Servidor escucha en `localhost:PUERTO`
- Web UI accesible vía navegador
- Desktop client opcional = wrapper (Electron/Tauri/PyWebView) que abre URL local + tray icon

### 5.2. Empaquetar Python+FastAPI+React en un instalador Windows

Flujo recomendado:
1. Backend: Python+FastAPI+Uvicorn → PyInstaller `--onedir` → `dist/lbamonitor/`
2. Frontend: React build → `vite build` → `static/`
3. FastAPI sirve `static/` con `StaticFiles`
4. Inno Setup crea instalador que:
   - Copia `dist/lbamonitor/` a `C:\Program Files\LBAMonitor\`
   - Registra servicio Windows (NSSM)
   - Crea accesos directos
5. Opcional: app desktop PyWebView/Tauri/Electron que abre la URL

### 5.3. Correr FastAPI como servicio Windows

#### Opción 1: NSSM (RECOMENDADA)
- Descargar `nssm.exe`, ejecutar `nssm install LBAMonitor`
- Apuntar a `lbamonitor.exe` (PyInstaller)
- NSSM maneja crashes, auto-restart, logs

#### Opción 2: pywin32 `win32serviceutil.ServiceFramework`
- Subclass `ServiceFramework`, `SvcDoRun` arranca uvicorn programáticamente
- PyInstaller + pywin32 service requiere tricks (metallapan.se)

#### Opción 3: WinSW
- YAML config + `winsw.exe` → wrap cualquier .exe como servicio
- Más simple que NSSM para CI/CD

### 5.4. Tauri vs Electron vs PyWebView

| Aspecto | Tauri 2 | Electron 42 | PyWebView |
|---|---|---|---|
| Backend | Rust (sidecar) | Node.js | Python (mismo proceso) |
| Renderer | WebView nativo | Chromium bundled | WebView nativo |
| Tamaño binario | ~600 KB core | ~80-150 MB | ~20-30 MB |
| RAM idle | 30-40 MB | 200-300 MB | 30-50 MB |
| Madurez 2025/26 | ★★★★ | ★★★★★ estándar | ★★★ |

**Recomendación LBAMonitor**:
- **Opción A (más simple)**: No usar app desktop. Servidor + web UI + navegador (como Sonarr)
- **Opción B (mejor UX)**: **PyWebView 5** como wrapper mínimo (30 MB) con tray icon. Mantiene todo en Python.
- **Opción C (moderno)**: Tauri con sidecar. Binarios minúsculos pero más complejo.
- **❌ Evitar Electron**: 200+ MB absurdo cuando backend ya pesa 50 MB.

### 5.5. Comunicación desktop ↔ servicio local

| Mecanismo | Pros | Contras | Veredicto |
|---|---|---|---|
| HTTP local (127.0.0.1:8123) | Estándar, debuggable | Overhead TCP ~30% | ★★★★★ **default** |
| WebSocket | Push real-time | Más código | ★★★★ complemento |
| Named Pipes | 16% más rápido | Complejo, firewall | ★★★ |
| Shared memory | Máximo rendimiento | Complejo | ★★ |

**Recomendación**: HTTP local + WebSocket para eventos push. Suficiente para 99% de casos.

### 5.6. Arquitectura final LBAMonitor

```
┌────────────────────────────────────────────┐
│  Servicio Windows (NSSM + lbamonitor.exe)  │
│  ┌──────────────────────────────────────┐  │
│  │  FastAPI + Uvicorn (Python)          │  │
│  │  ├── REST API (/api/...)             │  │
│  │  ├── WebSocket /ws (eventos USB)     │  │
│  │  ├── SQLite + SQLAlchemy async       │  │
│  │  ├── Watcher USB (WMI events)        │  │
│  │  ├── MTP (comtypes + Heribert17/mtp) │  │
│  │  └── StaticFiles (React build)       │  │
│  └──────────────────────────────────────┘  │
└────────────────────────────────────────────┘
              ↑ HTTP/WS @ 127.0.0.1:8123
              │
   ┌──────────┴──────────────────────┐
   │                                 │
┌──┴────────────┐         ┌──────────┴──────────┐
│  Navegador    │         │  PyWebView (tray)   │
│  (web UI)     │         │  opcional, 30 MB    │
└───────────────┘         └─────────────────────┘
```

---

## 6. Sistemas de licencia por hardware

### 6.1. Generar Machine ID estable en Windows

| Clase WMI | Campo | Estabilidad |
|---|---|---|
| Win32_Processor | ProcessorId | ★★★★★ (cambia solo al cambiar CPU) |
| Win32_BIOS | SerialNumber | ★★★★★ (cambia al flashear BIOS o cambiar mobo) |
| Win32_BaseBoard | SerialNumber | ★★★★ (cambia al cambiar motherboard) |
| Win32_DiskDrive | SerialNumber | ★★★ (cambia al reemplazar disco) |
| Win32_ComputerSystemProduct | UUID | ★★★★ (derivado SMBIOS) |

**Algoritmo recomendado**:
1. Recolectar 3-4 valores
2. Concatenar con separadores
3. SHA-256
4. Base32/base36 → string ~50 chars = **HWID**

Ventaja de 3-4 componentes: si uno cambia (reemplazo disco), permitir reactivación con tolerancia (3 de 4 coinciden).

### 6.2. Librerías Python para licensing

| Librería | Función | Estado |
|---|---|---|
| **PyArmor** | Ofuscación bytecode + bind a máquina + expiración offline | Mantenido (v9.2.6), pago para uso comercial |

### 6.3. Mejores prácticas para licencias offline (Cuba)

**Modelo recomendado**:
1. Generación HWID local al instalar
2. Usuario copia HWID y lo envía al licensor por WhatsApp/SMS/recarga
3. Licensor genera **license file firmado** con clave privada RSA-2048 (offline)
4. License file: `{HWID, expira, features, firma_RSA}`
5. App valida: cargar → verificar firma con clave pública embebida → comparar HWID → check fecha
6. **Sin telemetría**, sin llamadas home — todo offline

**Esquema simple sin RSA** (suficiente para amenaza baja):
- Licencia = `HMAC-SHA256(clave_secreta, "HWID|expira|features")` + payload
- Clave secreta embebida (ofuscada con PyArmor)
- Vulnerable a reverse engineering sofisticado, pero suficiente para copisterías cubanas

**Nivel pro**: RSA-2048 + clave privada NUNCA en binario del cliente. Solo clave pública. Inquebrantable sin la clave privada.

### 6.4. Recomendación LBAMonitor

1. **HWID**: SHA-256(ProcessorId + BIOS.SerialNumber + BaseBoard.SerialNumber + ComputerSystemProduct.UUID)
2. **Licencia**: file JSON firmado HMAC-SHA256 (`license.lic`)
3. **Ofuscación**: PyArmor para módulo de validación de licencia + lógica core
4. **Distribución**: WhatsApp/recarga saldo (como PAQUETECOPIES, 16/año)
5. **Tolerancia**: 3 de 4 componentes HWID coinciden → reactivar sin llamada al licensor

### 6.5. Gotchas

- `Win32_BIOS.SerialNumber` puede ser "To be filled by O.E.M." en PCs clónicas cubanas → usar fallback `ComputerSystemProduct.UUID`
- PyArmor **solo ofusca código propio**, NO terceros (numpy, pandas)
- VirtualBox/VMware devuelven HWIDs spoofeables → detectar `Win32_ComputerSystem.Model` = "VirtualBox" / "VMware" y bloquear
- En Cuba las leyes sobre software propietario están desactualizadas → la protección técnica (ofuscación + HWID) es más importante que la legal

---

## 7. Empaquetado Python para Windows en 2026

### 7.1. Estado de las herramientas

| Herramienta | Versión 2025/26 | Estado | Tamaño | Startup |
|---|---|---|---|---|
| **PyInstaller** | 6.x | ★★★★★ estándar de facto | 30-80 MB | ~2-5 s |
| **Nuitka** | 2.x | ★★★★ en ascenso | 40-100 MB | ~1-3 s |
| **cx_Freeze** | 7.x | ★★★ estable | Similar PyInstaller | ~8 s (lento) |
| **PyOxidizer** | 0.24+ | ★★ casi estancado | Compacto | Rápido |
| **Briefcase** (BeeWare) | 0.3.x | ★★★ | Similar PyInstaller | Similar |

**Recomendación**: **PyInstaller 6.x** para LBAMonitor. Mejor soporte para dependencias binarias (pywin32, comtypes).

### 7.2. PyInstaller 6+ notas

- Soporta Python 3.8-3.13
- `--onedir` recomendado para apps grandes — **más rápido startup** y mejor Windows Defender reputation que `--onefile`
- `--onefile` más lento al arrancar (extrae a temp) y **dispara más alerts de AV**
- Hooks para imports dinámicos: pywin32, comtypes, sqlalchemy, uvicorn requieren `--hidden-import`

### 7.3. Firma de código con certificado EV

#### Estado 2025
- Desde junio 2023, **certificados OV ya no evitan SmartScreen**
- **EV (Extended Validation)** = necesario para reputación inmediata
- Cambio 2024-2025: CAs **ya no permiten exportar EV certs a .pfx** — deben residir en **hardware token USB** o **cloud HSM**

#### Proceso
1. Comprar EV cert (~$300-700/año) a DigiCert, SSL.com, Sectigo, GlobalSign
2. Recibir token USB o configurar cloud HSM
3. Firmar con `signtool.exe`:
   ```
   signtool sign /fd sha256 /tr http://timestamp.digicert.com /td sha256 /sha1 <thumbprint> lbamonitor.exe
   ```

#### Para Cuba (sin acceso fácil a CAs internacionales)
- Self-signed: funciona si distribuyes certificado raíz al cliente (engorroso)
- Realidad: sin EV cert, los usuarios verán SmartScreen "Windows protected your PC". En Cuba ya están acostumbrados → tolerable.

### 7.4. Inno Setup vs WiX vs NSIS

| Herramienta | Curva | Output | Veredicto |
|---|---|---|---|
| **Inno Setup** | ★★★★★ fácil (Pascal-like) | `.exe` installer | ★★★★★ **default LBAMonitor** |
| WiX Toolset | ★★ difícil (XML verbose, .msi) | `.msi` | ★★★ solo si necesitas MSI enterprise |
| NSIS | ★★★ medio (script propio) | `.exe` | ★★★★ alternativa válida |

**Recomendación**: Inno Setup. Curva baja, output `.exe` autocliente, se integra bien con PyInstaller.

### 7.5. Tamaño típico .exe Python+FastAPI+SQLAlchemy+Pillow+matplotlib

Estimación por componente (PyInstaller `--onedir`, sin UPX):

| Componente | Tamaño |
|---|---|
| Python 3.12 runtime + stdlib | ~15 MB |
| pywin32 (completo) | ~10 MB |
| FastAPI + Starlette + Pydantic 2 + Uvicorn | ~5 MB |
| SQLAlchemy 2.x | ~5 MB |
| Pillow | ~10 MB |
| matplotlib | ~40 MB |
| comtypes + Heribert17/mtp | ~3 MB |
| PyArmor runtime | ~2 MB |
| **Total** | **~90 MB** |

Con UPX (~30-50% reducción): **~50-60 MB**.

**Sin matplotlib** (que es enorme): baja a **~50 MB** sin UPX, **~30 MB** con UPX.

> **Recomendación**: si no necesitas gráficas complejas, **eliminar matplotlib** y usar Recharts en el frontend. Reduce el binario 40 MB.

### 7.6. Cómo reducir tamaño

1. Excluir módulos no usados en `.spec`: `excludes = ['tkinter', 'unittest', 'pydoc', 'matplotlib.tests', 'numpy.tests']`
2. UPX compression (30-50% reducción)
3. `--onedir` en vez de `--onefile`: mejor startup, mejor reputación AV
4. Eliminar pandas si no se usa
5. Usar `--strip` en binarios (Linux, no Windows)

### 7.7. Recomendación LBAMonitor

- PyInstaller 6.x con `--onedir` + `.spec` con `excludes` explícitas
- UPX habilitado
- Inno Setup para installer final
- **Sin matplotlib** (usar Recharts en web UI)
- Firma EV si presupuesto permite; si no, aceptar SmartScreen
- **Tamaño objetivo**: 40-60 MB installer

### 7.8. Gotchas

- **Windows Defender False Positives**: PyInstaller `--onefile` es flag-systemically como malware. Mitigaciones: `--onedir`, firmar EV, submit a Microsoft for false positive review.
- `pywin32` requiere postinstall: `pywin32_postinstall.py -install`. PyInstaller lo maneja con hook correcto.
- `comtypes` genera caché de tipos en `gen_py/` — excluir del bundle y regenerar en runtime.
- SQLAlchemy 2.0 con Cython extensions puede romper PyInstaller — usar `SQLALCHEMY_DISABLE_C_EXTENSIONS=1` si issues.

---

## 8. Casos de uso reales en Cuba / América Latina

### 8.1. Copisterías en Cuba

**Modelo de negocio**:
- Paqueteros: distribuyen Paquete Semanal a domicilio. Precio: 1-5 CUC (pre-2021) / 200-350 CUP (2024-25)
- Puntos de venta / copisterías: 2 CUC por copiar paquete completo (~1 TB)
- Copiadores de series (sub-nicho): 30-80 CUP por copia, según día y región

**Inversión típica paquetero**: ~1000 USD en piezas de PC. Un paquetero reporta copiar **80 veces** el paquete por semana.

**Volumen Paquete Semanal**: ~1 TB distribuido cada semana, organizado en carpetas: Animados, Películas Full HD, Shows, Series, Aplicaciones, Música, etc.

### 8.2. Modelo de cobro por GB

**Precios típicos (CUP, 2024-25)**:
- Copia Paquete Semanal completo (1 TB): 200-350 CUP (~0.6-1 USD)
- Por GB individual: no es común — se cobra por contenido o por copia completa
- Por tiempo (cibercafé): 0.50-1 CUP/minuto histórico, hoy ~5-10 CUP/hora

**Estimación LBAMonitor**: si cobras por GB copiado en Cuba:
- 0.30-0.50 CUP/GB paquete semanal
- 1-2 CUP/GB contenido personalizado
- 5-10 CUP/GB software/apps

### 8.3. El Paquete Semanal

**Definición**: compendio ~1 TB material digital (películas, series, novelas, shows, música, apps, YouTube, classifieds, revistas) distribuido desde ~2008 en Cuba como **sustituto offline del internet**. No requiere internet ni antenas — basta con enchufar disco y transferir.

**Flujo**:
1. Productores (La Habana) arman el paquete cada semana (sin política, sin pornografía)
2. Distribuidores mayoristas compran y replican en discos
3. Paqueteros locales recogen discos de clientes, copian, devuelven al día siguiente
4. Copisterías / kioscos: PC con varios puertos USB, cliente llega con memoria, paga, le copian

**Herramientas usadas**:
- Copia nativa de Windows (lenta)
- PAQUETECOPIES (cuba, Roger Peña) — copia paralela
- MIRON (cuba) — monitorea qué se copió, multi-puesto con QR
- SUPERCOPY (cuba) — incluye copia a móviles

**Legalidad**: técnicamente ilegal pero tolerada. En 2024 hubo confiscaciones y pánico por Decreto 107, pero gobierno negó prohibir el Paquete.

### 8.4. Oportunidad para LBAMonitor

**Nicho real**:
- **Cuba**: copisterías de Paquete Semanal. **MIRON es el único competidor serio** y tiene barreras (sin web pública, sin documentación). Brecha enorme para un sucesor mejor.
- **Venezuela**: cibercafés declinando pero kioscos de descarga sobreviven.
- **Resto LatAm**: muy saturado de software genérico; no competir.

**Feature diferencial clave**: **soporte MTP** (copiar a celulares Android) — algo que el software de cibercafé genérico no hace, y que es crucial en Cuba donde los celulares son el dispositivo principal.

### 8.5. Recomendación para LBAMonitor

1. **Mercado primario**: copisterías cubanas de Paquete Semanal
2. **Mercado secundario**: copisterías venezolanas y zonas rurales LatAm sin internet
3. **No competir** en cibercafé gaming (Antamedia, SENET dominan)
4. **Feature must-have**: detección MTP (celulares), multi-puesto con QR (como MIRON), reporte diario
5. **Modelo de cobro**: licencia anual por máquina, pagadera por recarga saldo (como PAQUETECOPIES: 16/año) — accesible en Cuba
6. **Idiomas**: español primero, inglés después

### 8.6. Gotchas

- **ETECSA** (telecom estatal cubana) rebaja tarifas periódicamente → el Paquete Semanal pierde relevancia a largo plazo. Planear roadmap con esto en mente: añadir features de **gestión de copias de cualquier tipo**, no solo paquete.
- **Decreto 107 / confiscaciones 2024**: el negocio del paquete es legalmente precario. El software LBAMonitor debe ser vendible como "gestión general de copistería", no como "gestión de piratería".
- **Internet en Cuba es caro y lento**: la activación online de licencias es inviable. **Todo debe ser offline**.
- **Hardware en Cuba es antiguo**: PCs con 4 GB RAM, Windows 7/10. El software debe funcionar en **Windows 7+ con 4 GB RAM**, no asumir 16 GB.

---

## 9. Resumen de decisiones arquitectónicas

### Stack recomendado

| Capa | Tecnología | Justificación |
|---|---|---|
| Lenguaje | **Python 3.12+** | MTP/WPD solo viable en Python; pywin32 gold standard |
| Backend | **FastAPI + Uvicorn** | Async, OpenAPI, integra con watchdog/WMI |
| ORM | **SQLAlchemy 2.x async + Alembic** | Madurez, control fino SQLite WAL |
| DB | **SQLite WAL** | Sin servidor, embebido, ideal app local |
| Detección USB | **WMI events** (`Win32_DeviceChangeEvent`) + `pywin32` | Headless-friendly, sin ventana |
| MTP | **`Heribert17/mtp`** + `comtypes` | Único mantenido (2025.3.10) |
| Filesystem watch | **`watchdog`** con debouncer custom 500ms | Estándar, cuidado buffer overflow |
| Empaquetado | **PyInstaller 6 `--onedir` + UPX + Inno Setup** | Estándar, 40-60 MB installer |
| Servicio Windows | **NSSM** sobre binario PyInstaller | Más simple que pywin32 service |
| Desktop admin | **PyWebView 5** (tray icon) | 30 MB wrapper, no Electron |
| Comunicación | **HTTP REST + WebSocket** en `127.0.0.1:8123` | Estándar, suficiente |
| Licencia | **HWID SHA-256** + license file **HMAC-SHA256 firmado** + **PyArmor** ofuscación | 100% offline, Cuba-friendly |
| Firma de código | **EV cert** (si presupuesto) o self-signed + SmartScreen tolerance | — |

### Decisiones NO tomar

- ❌ No usar Node.js para nada crítico
- ❌ No usar Electron — 200+ MB absurdo
- ❌ No usar `--onefile` PyInstaller — falsos positivos AV
- ❌ No usar watchdog sobre el pendrive para contar bytes — buffer overflow garantizado con Paquete Semanal
- ❌ No depender de `usb-detection` npm — deprecated
- ❌ No competir con Antamedia/SENET en cibercafé genérico
- ❌ No asumir internet del cliente — todo offline
- ❌ No asumir hardware moderno — soportar Windows 7/10 con 4 GB RAM

### Competidor principal a batir

**MIRON** (mironcuba.com) — ya hace: detección multi-dispositivo (USB/discos/celulares), multi-puesto con QR, catálogo de audiovisuales, reporte diario. **LBAMonitor debe mejorar en**: mejor UX web, mejor soporte MTP, transparencia (web pública), modelo de licencias más accesible.

---

## Fuentes principales consultadas (selección)

- mironcuba.com / play.google.com/store/apps/details?id=com.itego.MironApp
- vistarmagazine.com/herramienta-numero-uno-paquete
- cubanet.org/el-paquete-semanal-se-perfecciona
- ipscuba.net/espacios/del-paquete-semanal-y-los-copiadores-de-series-en-cuba
- paquetesemanal.eltoque.com / en.wikipedia.org/wiki/El_Paquete_Semanal
- abdus.dev/posts/python-monitor-usb / timgolden.me.uk/python/win32_how_do_i/detect-device-insertion.html
- github.com/Heribert17/mtp / dropbox.tech/infrastructure/adventures-with-comtypes
- pyinstaller.org/en/v6.3.0/usage.html
- stackoverflow.com/questions/65591630 (FastAPI Windows service + NSSM)
- tech-insider.org/tauri-vs-electron-2026 / digitalapplied.com/blog/desktop-apps-web-stack-tauri-electron-deno-wails-2026
- pyarmor.readthedocs.io/en/latest/licenses.html
- tewarid.github.io/2015/07/30/generating-a-unique-id-for-a-windows-pc
- antamedia.com / cybersquare.com.br / tenaxsoft.com / cbm.com.ar
- learn.microsoft.com/en-us/windows/win32/wpd_sdk / learn.microsoft.com/en-us/samples/microsoft/windows-classic-samples/portable-devices-com-api

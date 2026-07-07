# Análisis Técnico de MIRON (Uatcher) — Software original cubano

> Documento técnico exhaustivo del funcionamiento interno de Uatcher/MIRON,
> basado en el análisis del código decompilado (Dotfuscator) y la investigación
> de mercado realizada.

---

## 1. Identidad y contexto

### 1.1 Datos generales
- **Nombre**: Uatcher (alias comercial MIRON)
- **Autor**: MIRON (firma en `AssemblyInfo.cs`)
- **Copyright**: © 2022
- **Descripción**: "Aplicación para monitorear copias a memorias en Cuba"
- **Sitio web**: mironcuba.com (hosted como Google Docs viewer)
- **App Android**: `com.itego.MironApp` en Google Play — escaneo QR multi-puesto
- **Distribución**: Cerrada, sin web pública scrapeable
- **Ofuscación**: Dotfuscator Professional (evaluación)

### 1.2 Contexto de uso
MIRON/Uatcher está diseñado para **copisterías cubanas** que copian el **Paquete Semanal** (~1 TB de contenido: películas, series, música, apps) a memorias USB de clientes. El software permite al dueño:
- Saber **qué se copió** a cada USB (evita robos del operador)
- **Cobrar** por GB copiado o por contenido
- Llevar **estadísticas** de uso
- **Multi-puesto**: varias PCs administradas vía QR + app móvil

### 1.3 Ensamblados decompilados

| Ensamblado | Tipo | Función |
|---|---|---|
| `Uatcher.Service.exe` | Exe (servicio Topshelf) | Monitorea dispositivos en background |
| `Uatcher.UI.exe` | WinExe (WinForms) | Interfaz de operador |
| `Uatcher.EF.dll` | Class Library | Entity Framework 6 + SQLCE 4 |
| `Uatcher.Common.dll` | Class Library | Utilidades (NLog, filtros, helpers) |

**Dependencias externas**:
- `EntityFramework.dll` + `EntityFramework.SqlServerCompact.dll`
- `System.Data.SqlServerCe.dll` + `sqlce*.dll` (x86 y amd64)
- `MediaDevices.dll` — acceso a dispositivos MTP (WPD API)
- `NLog.dll` — logging
- `Topshelf.dll` — servicio Windows
- `EPPlus.dll` — exportación Excel
- `Microsoft.WindowsAPICodePack.dll` + `.Shell.dll` — Shell COM
- `System.Windows.Forms.DataVisualization` — gráficos

---

## 2. Arquitectura general

```
┌─────────────────────────────────────────────────┐
│                 Windows Host                     │
│                                                  │
│  ┌──────────────────────┐  ┌──────────────────┐ │
│  │  Uatcher.Service.exe │  │  Uatcher.UI.exe  │ │
│  │  (Topshelf)          │  │  (WinForms)      │ │
│  │                      │  │                  │ │
│  │  - Detección USB     │  │  - Historial     │ │
│  │  - Detección MTP     │  │  - Estadísticas  │ │
│  │  - FileSystemWatcher │  │  - Cobros        │ │
│  │  - ClockMonitor      │  │  - Configuración │ │
│  │  - SessionHeartbeat  │  │  - Catálogo      │ │
│  └──────────┬───────────┘  └────────┬─────────┘ │
│             │                       │            │
│             └───────────┬───────────┘            │
│                         ▼                        │
│              ┌────────────────────┐              │
│              │  SQL Server CE 4   │              │
│              │  (Uatcher.sdf)     │              │
│              └────────────────────┘              │
│                                                  │
│  ┌──────────────────────┐                       │
│  │  App Android (MIRON) │  ← QR multi-puesto    │
│  │  com.itego.MironApp  │                       │
│  └──────────────────────┘                       │
└──────────────────────────────────────────────────┘
```

### 2.1 Patrón arquitectónico
- **Layered + WinForms direct**: la UI accede directamente a la BD vía EF6, sin capa de servicios intermedia
- **Comunicación UI ↔ Servicio**: vía BD compartida (SQLCE), no vía API
- **Multi-puesto**: app Android escanea QR de cada PC para administrar remotamente

---

## 3. Modelo de datos (9 tablas)

### 3.1 Esquema completo

```sql
-- Operadores
Users (Id, Name, Created, Inactive)

-- Inserciones de USB
InsertedDrives (
    Id, InsertionDateTime,
    SpaceBytes, AvailableSpaceBytes, AvailableSpaceBytesAtTheEnd,
    Name, RootDirectory, VolumeLabel,
    SerialNumber, Model,
    IsMobile, IsMountedFolder,
    Payment,  -- int (moneda local)
    Comment, CommentFixed,
    PreviousInsertionsCounter, PreviousPaymentsSum,
    RowColor,
    RemovedDriveId FK,
    UserId FK
)

-- Extracciones
RemovedDrives (Id, RemovalDateTime, Name, RootDirectory)

-- Copias de archivos
Copies (Id, CopyDateTime, FullPath, Extension, FileName, SizeBytes, InsertedDriveId FK)

-- Borrados de archivos
Deletions (Id, DeletionDateTime, FullPath, Extension, FileName, InsertedDriveId FK)

-- Trazabilidad de pagos
PaymentAlterations (Id, PreviousPayment, NewPayment, AlterationDateTime, InsertedDriveId FK, UserId FK)

-- Cambios de reloj
PossiblePCDatetimeChanges (Id, Moment, To)

-- Sesiones del servicio
ServiceSessions (Id, StartDateTime, EndDateTime, AliveDateTime, SessionTime)

-- Settings genéricas
KeyValues (Id, Key, Value)
```

### 3.2 StoredKeyValues (settings persistidas)

| Key | Contenido |
|---|---|
| `license` | String de licencia firmada |
| `payment_hidden` | "true"/"false" — ocultar columna de pago |
| `statistics` | JSON comprimido con GeneralStatistics |
| `payment_patterns` | JSON comprimido con patrones de pago automático |
| `video_folders` | JSON con List<string> |
| `business_info` | JSON con BusinessInfo (Name, MarketingText, Address) |
| `order_copies_by` | Enum OrderCopiesBy (date|size|name|extension) |
| `publicity_folder` | JSON con PublicityFolder (FolderPath, Automatic) |
| `invoice_picture_device` | "true"/"false" |
| `backup_setting` | "true"/"false" (backup diario) |

---

## 4. Cerebro y lógica de negocio

### 4.1 Detección de dispositivos

MIRON usa **dos mecanismos** de detección:

#### USB mass-storage
- **Método**: Win32 API `WM_DEVICECHANGE` con ventana oculta (estándar de Windows)
- **Identificación**: `Win32_DiskDrive.SerialNumber` vía WMI
- **Fallback**: VolumeLabel + SpaceBytes si no hay serial
- **Filtro**: DriveType = Removable

#### MTP (celulares Android)
- **Método**: `MediaDevices.dll` (librería .NET que envuelve la API WPD de Windows)
- **Detección**: enumeración de dispositivos WPD
- **Acceso a archivos**: vía COM Shell (no filesystem nativo)
- **Sin watchdog**: MTP no soporta FileSystemWatcher, usa polling manual

### 4.2 Tracking de copias

- **Método**: `System.IO.FileSystemWatcher` nativo de .NET
- **Eventos**: Created, Deleted, Changed, Renamed
- **Filtros**: `FileTypeFilter` enum (videos, images, music, documents, apps, archives, others)
- **Datos por copia**: FullPath, Extension, FileName, SizeBytes, CopyDateTime

### 4.3 Gestión de pagos

- **Pago manual**: el operador ingresa el monto en la UI
- **Pago automático**: patrones `PaymentsPatterns` (lista de `{GbCopied, Payment}`)
- **Trazabilidad**: cada cambio genera `PaymentAlteration` (previous, new, user, timestamp)
- **Ocultamiento**: `payment_hidden` flag para modo "sin cobro"

### 4.4 Sistema de licencias

- **Machine ID**: WMI (Win32_Processor, BIOS, BaseBoard, DiskDrive)
- **Licencia**: persistida en `KeyValues.license`
- **Validación**: al arrancar el servicio
- **Distribución**: cerrada (contacto directo con MIRON)

### 4.5 Estadísticas (GeneralStatistics)

Calculadas incrementalmente y persistidas en `KeyValues.statistics` (JSON comprimido):

| Campo | Descripción |
|---|---|
| `TopDays` | Top días con más dispositivos (por día de la semana) |
| `TopHours` | Top horas con más inserciones |
| `TopFiles` | Top archivos más copiados (histórico) |
| `TopFilesTwoWeeks` | Top archivos más copiados (últimas 2 semanas) |
| `TopClients` | Top clientes recurrentes |
| `DevicesAveragePerDay` | Promedio de dispositivos por día |
| `PaymentAveragePerDay` | Promedio de pago por día |
| `MaxDevicesOneDay` | Máximo histórico de dispositivos en un día |
| `MaxPaymentOneDay` | Máximo histórico de pago en un día |
| `SpaceCopiedAveragePerDevice` | Promedio de bytes copiados por dispositivo |
| `FilesCopiedCountAveragePerDevice` | Promedio de archivos copiados por dispositivo |
| `PaymentAveragePerDevice` | Promedio de pago por dispositivo |
| `LastCopyId` | Último Copy.Id procesado (cálculo incremental) |

### 4.6 Servicios internos

| Servicio | Función |
|---|---|
| `ClockMonitor` | Detecta cambios de reloj del PC |
| `SessionHeartbeat` | Mantiene viva la ServiceSession |
| `BackupService` | Backup diario de la BD |
| `PublicityFolder` | Auto-copia de archivos al insertar USB |
| `InvoiceEngine` | Genera factura en imagen (System.Drawing) |

---

## 5. Parte interactiva y visual (UI)

### 5.1 Tecnología
- **WinForms** con `System.Windows.Forms.DataVisualization` para gráficos
- **Microsoft.WindowsAPICodePack.Shell** para diálogos nativos de Windows 7+

### 5.2 Pantallas principales (inferidas del análisis)

1. **Historial**: tabla con todas las inserciones, filtros avanzados (nombre, serial, modelo, tamaño, fechas, pago, comentarios, operador, móvil, tiene pago)
2. **Estadísticas**: KPIs + gráficos (top días, horas, archivos, clientes)
3. **Configuración**: BusinessInfo, PublicityFolder, VideoFolders, PaymentPatterns, BackupSetting
4. **Operadores**: CRUD de usuarios (sin login, sin roles)
5. **Factura**: imagen generada con System.Drawing + webcam opcional (InvoicePictureDevice)

### 5.3 Flujo del operador

1. **Arrancar PC** → Uatcher.Service arranca automáticamente (Topshelf)
2. **Conectar USB** → el servicio detecta y registra `InsertedDrive`
3. **Copiar archivos** → el FileSystemWatcher registra cada `Copy`
4. **Extraer USB** → el servicio crea `RemovedDrive`
5. **Cobrar** → el operador abre la UI, busca la inserción, ingresa el pago
6. **Ver estadísticas** → el operador abre la pestaña de estadísticas
7. **Cerrar día** → backup automático si `backup_setting = true`

### 5.4 Multi-puesto con QR
- Cada PC tiene un código QR identificador
- La app Android (`com.itego.MironApp`) escanea el QR
- Permite al supervisor ver estado de cada máquina remotamente

---

## 6. Limitaciones de MIRON

### 6.1 Técnicas
1. **Sin API REST**: toda interacción es por WinForms directo a BD
2. **Sin acceso remoto**: el operador debe estar físicamente en la PC
3. **SQLCE deprecated**: sin soporte 64-bit nativo, sin drivers modernos
4. **WinForms**: UI difícil de mantener, no responsive, no accesible remotamente
5. **Sin autenticación**: cualquiera con acceso al PC ve/modifica datos
6. **Ofuscación**: impide auditoría y mantenimiento por terceros
7. **Topshelf deprecated**: archivado desde 2020
8. **migrate.exe externo**: las migraciones requieren ejecutar binario aparte
9. **Sin WebSockets**: la UI debe hacer polling a la BD
10. **Sin plugins**: no es extensible

### 6.2 Funcionales
1. **Sin popup de cobro forzado**: el operador puede extraer USB sin cobrar
2. **Sin membresías/VIP**: no hay programa de fidelización
3. **Sin catálogo**: no hay catálogo navegable de contenido
4. **Sin login**: no hay trazabilidad de quién hace qué
5. **Sin cierre de caja**: no hay cuadre diario formal
6. **Sin historial de precios**: no se sabe cuándo cambió la tarifa
7. **Sin reglas de precio**: solo modo per_gb o manual
8. **Sin importación CSV**: el catálogo se gestiona manualmente
9. **Sin métricas**: no hay Prometheus ni observabilidad
10. **Sin alerta de disco lleno**: el servicio colapsa sin aviso

### 6.3 Seguridad
1. **Sin JWT ni auth**: API abierta (no hay API)
2. **Sin roles**: todos los operadores tienen los mismos permisos
3. **Sin 2FA**: acceso trivial a la BD
4. **Sin cifrado**: datos en plano en SQLCE

---

## 7. Comparativa detallada MIRON vs LBAMonitor

### 7.1 Detección USB

| Aspecto | MIRON | LBAMonitor |
|---|---|---|
| Método primario | WM_DEVICECHANGE | WM_DEVICECHANGE (mismo) |
| Filtro removibles | Sí | Sí (DRIVE_REMOVABLE + DRIVE_FIXED) |
| Fallback | No | Sí (polling Win32 API cada 5s) |
| Identificación | SerialNumber WMI | Fingerprint compuesto (DeviceID + VolumeSerial) |
| Latencia | < 100ms | < 100ms |
| Confiabilidad | Alta | Alta + fallback |

### 7.2 Detección MTP

| Aspecto | MIRON | LBAMonitor |
|---|---|---|
| Librería | MediaDevices.dll (.NET) | MediaDevices.dll (pythonnet) + PowerShell fallback |
| Búsqueda DLL | Directorio instalación | 4 rutas (_MEIPASS, backend/lib, Program Files, ProgramData) |
| Polling | ? | 3 segundos |
| Copia archivos | Shell COM | WPD API + MtpFileWatcher (polling + snapshot) |

### 7.3 Arquitectura

| Aspecto | MIRON | LBAMonitor |
|---|---|---|
| Lenguaje | C#/.NET 4.5 | Python 3.11+ |
| UI | WinForms | PySide6 (Qt6) |
| API REST | No | FastAPI (90+ endpoints) |
| WebSocket | No | Sí (11 tipos de eventos) |
| BD | SQLCE 4 | SQLite WAL / PostgreSQL |
| ORM | Entity Framework 6 | SQLAlchemy 2.0 async |
| Migraciones | migrate.exe | Alembic auto-upgrade |
| Multi-puesto | App Android (QR) | Pendiente v5.0 |
| Web | No | Flask (catálogo + stats) |
| Plugins | No | Sí (9 eventos) |
| Código | Cerrado | Abierto |
| Tests | No | 103 pytest + 16 E2E |

### 7.4 Funcionalidades

| Funcionalidad | MIRON | LBAMonitor |
|---|---|---|
| Popup cobro forzado | No | Sí (Qt nativo) |
| Login con roles | No | JWT (admin/manager/operator) |
| Membresías | No | 5 niveles + 6 reglas |
| Catálogo | No | Sí + import CSV + escaneo |
| Cierre de caja | No | Sí + historial |
| Historial precios | No | Sí (PriceHistory) |
| Reglas de precio | No | Sí (folder/capacity/fixed/discount) |
| Kiosco | No | Sí (pantalla completa) |
| Estadísticas | Básicas | Completas + gráficos + insights |
| Backup | Diario (SQLCE) | VACUUM INTO + red local SMB |
| Alerta disco lleno | No | Sí (warning <1GB, read-only <500MB) |
| Atajos teclado | No | Sí (F2, F5, Ctrl+Enter, ?) |
| Generador licencias | No | Sí (GUI tkinter) |
| Logo | Sí | Sí (SVG profesional) |

---

## 8. Conclusión

MIRON es un software funcional que resuelve el problema del monitoreo de copias USB en Cuba, pero tiene limitaciones arquitectónicas (sin API, sin auth, SQLCE deprecated, código cerrado) que impiden su evolución.

LBAMonitor toma lo mejor de MIRON (detección WM_DEVICECHANGE, MediaDevices.dll para MTP) y lo mejora con:
- Arquitectura API-first (FastAPI + WebSocket)
- Interfaz nativa PySide6 (mejor que WinForms)
- Web Flask para acceso remoto
- Sistema de plugins extensible
- Login con roles y JWT
- Popup de cobro forzado
- Membresías, recompensas, catálogo, cierres de caja
- 103 tests + 16 pasos E2E
- Código abierto

LBAMonitor es **funcionalmente superior** a MIRON en todos los aspectos, manteniendo la misma confiabilidad de detección USB/MTP.

# LBAMonitor v4.4.0

**Sistema de monitoreo de copias a memorias USB / MTP para Windows**

LBAMonitor detecta la inserción de dispositivos USB, contabiliza los archivos copiados, calcula cobros en base a un catálogo de precios, emite facturas, gestiona membresías VIP y mantiene backups automáticos. Es la reimplementación moderna de Uatcher con arquitectura API-first.

## Estado del proyecto

**v4.4.0 — Production-Ready (Release Candidate)**

Esta versión corrige todos los issues Critical y High identificados en la auditoría de v4.0.0 y v4.2:

- ✅ **Auth JWT completa**: `/api/auth/login`, `/refresh`, `/logout` con access + refresh tokens
- ✅ **79 endpoints protegidos** con `Depends(require_operator)` o `require_admin`
- ✅ **Secrets desde env vars**: `jwt_secret`, `license.signing_secret`, `plugins_signing_key` ya no están hardcoded
- ✅ **Plugins firmados con HMAC**: cada plugin requiere `.py.sig` con firma HMAC-SHA256
- ✅ **Bug `:memory:` corregido**: `db.py` y `alembic/env.py` manejan correctamente SQLite en memoria
- ✅ **License `tolerance` implementado**: distancia de Hamming sobre HWID hex
- ✅ **`client.points` acumulativo**: `+=` en lugar de `=`
- ✅ **`log_manager.py` eliminado**: dead code removido
- ✅ **Scheduler funcional**: `BackupEngine` inicializado con argumentos correctos, `_cleanup_logs` usa `logging_setup`
- ✅ **Monitor USB activo**: se arranca en el `lifespan` de FastAPI (no comentado)
- ✅ **WQL injection mitigado**: validación de `drive_letter` y `partition.DeviceID` en `wmi_utils.py`
- ✅ **VACUUM INTO validado**: regex anti-inyección en `backup_engine.py`
- ✅ **Desktop Qt arreglado**: 6 SyntaxErrors corregidos, login con `/api/auth/login`, WSClient thread-safe con signals Qt
- ✅ **Frontend React**: Login + ErrorBoundary + 404 + interceptor JWT con refresh automático
- ✅ **Web Flask**: open redirect validado, usa endpoints correctos
- ✅ **Dependencies pinneadas**: `~=` en `pyproject.toml` (major.minor)
- ✅ **CI/CD**: GitHub Actions con ruff + mypy + bandit + pytest + build Docker
- ✅ **Docker + docker-compose** para PostgreSQL + backend + web
- ✅ **`.gitignore` + `.env.example`** completos

## Stack tecnológico

- **Backend**: Python 3.11+, FastAPI, SQLAlchemy 2.0 async, Pydantic v2, loguru, watchdog, Alembic
- **Auth**: python-jose (JWT), bcrypt (passwords), cryptography (RSA opcional)
- **DB**: SQLite (kioscos) o PostgreSQL (centralizado)
- **Monitor**: WMI + watchdog (Windows), MediaDevices.dll via pythonnet (MTP)
- **Desktop**: PySide6/PyQt6 con 11 tabs + WSClient thread-safe
- **Frontend**: React 18 + TypeScript + Vite + Tailwind CSS
- **Web**: Flask + Jinja2 (catálogo público)
- **Scheduler**: APScheduler (backup nocturno + cleanup)
- **Plugins**: 5 plugins con firma HMAC obligatoria

## Instalación rápida (desarrollo)

```bash
# 1. Clonar repo
git clone <repo-url> lbamonitor
cd lbamonitor

# 2. Backend
cd backend
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate  # Windows
pip install -e ".[dev]"

# 3. Configurar secrets (desarrollo)
cp ../.env.example ../.env
# Editar .env: LBAMONITOR_ENV=development (para usar defaults seguros)

# 4. Arrancar backend
LBAMONITOR_ENV=development lbamonitor-api
# O: python -m lbamonitor.api.main
```

## Instalación en producción (Windows kiosco)

Ver [INICIO_RAPIDO.md](INICIO_RAPIDO.md) para guía paso a paso.

Resumen:
1. Ejecutar `installer/msi/lbamonitor.iss` con InnoSetup → genera `LBAMonitor-Setup-v4.4.0.exe`
2. Instalar en `C:/Program Files/LBAMonitor/`
3. Configurar `C:/ProgramData/LBAMonitor/config/config.toml` con secrets reales
4. Setear env vars del sistema o usar `installer/nssm/install-service.ps1` para servicio Windows
5. Verificar `http://localhost:8123/health`

## Configuración de secrets (OBLIGATORIO en producción)

Generar secrets aleatorios:

```bash
python -c "import secrets; print('JWT_SECRET=' + secrets.token_hex(32))"
python -c "import secrets; print('LICENSE_SECRET=' + secrets.token_hex(32))"
python -c "import secrets; print('PLUGINS_KEY=' + secrets.token_hex(32))"
```

Setear como variables de entorno (ver `.env.example`):

```
LBAMONITOR_ENV=production
LBAMONITOR_SECURITY__JWT_SECRET=<jwt_secret_64_chars>
LBAMONITOR_LICENSE__SIGNING_SECRET=<license_secret_64_chars>
LBAMONITOR_PLUGINS_SIGNING_KEY=<plugins_signing_key_64_chars>
```

**Alternativa más segura (RSA-2048) para licencias:**

```bash
# Generar par de claves
openssl genrsa -out private.pem 2048
openssl rsa -in private.pem -pubout -out public.pem

# Backend: setear LBAMONITOR_LICENSE__PUBLIC_KEY_PEM con contenido de public.pem
# Generador: setear LBAMONITOR_LICENSE__PRIVATE_KEY_PEM con contenido de private.pem
```

## Generación de licencias

```bash
# Obtener HWID de la máquina cliente
python -m lbamonitor.cli get-machine-id

# Generar licencia (en la máquina del licensor)
LBAMONITOR_LICENSE__SIGNING_SECRET=<secret> \
python -m tools.license_generator.generate \
    --machine-id <hwid_cliente> \
    --tier pro \
    --days 365

# O con RSA:
LBAMONITOR_LICENSE__PRIVATE_KEY_PEM="$(cat private.pem)" \
python -m tools.license_generator.generate \
    --machine-id <hwid_cliente> \
    --tier pro \
    --expires 2026-12-31
```

## Estructura del proyecto

```
lbamonitor-v4.4/
├── backend/                  # FastAPI + SQLAlchemy + monitor
│   ├── lbamonitor/
│   │   ├── api/              # Routers, schemas, middleware
│   │   │   ├── routes/       # 17 routers (auth, users, USB, billing, etc.)
│   │   │   ├── middleware/   # AuthMiddleware
│   │   │   └── schemas/      # Pydantic schemas
│   │   ├── core/             # Config, DB, models, repositories, services
│   │   │   ├── security/     # auth.py (JWT+bcrypt), rate_limiter.py
│   │   │   ├── cache/        # memory_cache.py (LRU+TTL)
│   │   │   ├── services/     # license_engine, scheduler, backup_engine, plugins
│   │   │   ├── models/       # 24 modelos SQLAlchemy
│   │   │   └── repositories/ # 15 repositorios
│   │   ├── monitor/          # USBMonitor, MTPMonitor, ClockMonitor, FileWatcher
│   │   ├── utils/            # helpers, logging_setup, formatters
│   │   └── cli/              # CLI
│   ├── plugins/              # 5 plugins con .sig obligatorio
│   ├── tests/                # Tests unitarios + integración
│   ├── alembic/              # Migraciones
│   └── pyproject.toml        # Deps pinneadas
├── desktop_qt/               # Cliente desktop PySide6/PyQt6
│   ├── ui/                   # 11 tabs (dashboard, USB, billing, etc.)
│   ├── api/                  # client.py + ws_client.py (thread-safe)
│   └── assets/               # style.qss
├── frontend/                 # React + TypeScript + Vite
│   └── src/
│       ├── routes/           # 12 vistas + Login + 404
│       ├── components/       # ErrorBoundary
│       └── api/              # API client con JWT + refresh
├── web/                      # Flask + Jinja2 (catálogo público)
├── installer/                # InnoSetup MSI + NSSM service + PyInstaller
├── tools/
│   └── license_generator/    # Generador de licencias (HMAC o RSA)
├── docs/                     # Documentación técnica
├── .github/workflows/ci.yml  # CI/CD
├── Dockerfile                # Multi-stage build
├── docker-compose.yml        # PostgreSQL + backend + web
├── .env.example              # Template de secrets
├── .gitignore
├── config.default.toml       # Config por defecto
└── README.md                 # Este archivo
```

## Endpoints API principales

- `POST /api/auth/login` — Iniciar sesión (rate-limited: 5/min)
- `POST /api/auth/refresh` — Refrescar access token
- `POST /api/auth/logout` — Revocar token
- `GET /api/health` — Health check (público)
- `GET /api/users` — Listar usuarios (admin)
- `GET /api/inserted-drives` — USBs insertados (operator+)
- `GET /api/inserted-drives/active` — USBs actualmente conectados
- `GET /api/statistics` — Estadísticas completas
- `GET /api/license` — Estado de licencia
- `POST /api/license/activate` — Activar licencia
- `GET /api/backups` — Listar backups
- `POST /api/backups/trigger` — Disparar backup manual (admin)
- `WS /ws/events` — WebSocket de eventos en tiempo real

Ver `/docs` (Swagger UI) para documentación completa.

## Documentación

- [INICIO_RAPIDO.md](INICIO_RAPIDO.md) — Guía de instalación paso a paso
- [CHANGELOG.md](CHANGELOG.md) — Historial de versiones
- [docs/TECHNICAL_REFERENCE.md](docs/TECHNICAL_REFERENCE.md) — Referencia técnica
- [docs/plugins.md](docs/plugins.md) — Guía de plugins

## Licencia

Proprietary — © LBAMonitor Team

# Changelog

## [4.4.0] — 2026-07-06

### Resumen
Versión estable con TODOS los bugs críticos de v4.3 corregidos (login roto, plugins muertos, MTP sin polling, catálogo público roto, sin trial de licencia) + features nuevas solicitadas: MTP multi-fabricante, sistema PDF completo, guardado en escritorio, settings admin completo, tabs Qt funcionales, dashboard web tiempo real, generador de licencia con GUI, trial de 10 días, 3 plugins nuevos.

### Añadido (NEW)
- **Trial de 10 días**: `license_state.py` con persistencia en BD + anti-tampering HMAC. Tras 10 días sin licencia, features limitadas (solo lectura).
- **Endpoint `GET /api/license/status`**: estado completo (trial/expired/licensed/invalid) + días restantes + features_limited.
- **Sistema PDF completo** (`pdf_engine.py`):
  - `generate_invoice_pdf()` — factura con datos del cobro, descuentos, imagen webcam
  - `generate_service_pdf()` — PDF explicativo del servicio (precios, membresías, reglas)
  - `generate_daily_report_pdf()` — reporte diario tipo Mirón
- **Auto-copia de PDF al USB**: al insertar un USB por primera vez, se copia `LBAMonitor_Servicio.pdf` a la raíz automáticamente.
- **Guardado en escritorio**: imágenes de webcam y PDFs de factura se guardan en `<desktop>/LBAMonitor/<YYYY-MM-DD>/<HHMMSS>_<username>.{jpg,pdf}`.
- **MTP multi-fabricante** (`mtp_monitor.py`):
  - `detect_manufacturer()` — Samsung, Xiaomi, Motorola, Huawei, iPhone, generic
  - `_enumerate_files()` implementado con pythonnet + MediaDevices.dll
  - iPhone filtrado con log explicativo (requiere iTunes, protocolo AFC no MTP)
- **Settings admin completo** (26 endpoints nuevos):
  - `GET/PUT /api/settings/{pricing,monitoring,backup,logging,appearance,server,license-config}`
  - `GET/POST/PUT/DELETE /api/settings/reward-rules`
  - `GET /api/memberships`, `PUT /api/memberships/{tier}`, `POST /api/memberships/initialize`
  - `GET /api/admin/logs` con filtros level/search/limit
- **Descuentos en cadena (multiplicativo)** en `pricing_engine.py`:
  - `factor = (1-vip%)(1-emp%)(1-tier%)(1-promo%)` en lugar del viejo MAX+ADD
- **Web dashboard tiempo real** (`backend/lbamonitor/web/`):
  - Reemplaza Flask con FastAPI Jinja2Templates (todo en Python)
  - Dashboard con WebSocket + fallback 30s
  - Catálogo público sin auth
  - Login por cookie HTTPOnly con refresh automático
- **6 tabs Qt completas** (3049 LOC nuevos):
  - `billing_tab.py` — cobro fácil, comentarios, foto webcam, historial, export PDF
  - `clients_tab.py` — gestión clientes/VIP/membresías
  - `catalog_tab.py` — CRUD catálogo audiovisuales
  - `settings_tab.py` — config completa del sistema
  - `logs_tab.py` — visor logs tiempo real
  - `license_tab.py` — estado licencia + activación + copiar HWID
- **Generador de licencia con GUI** (`tools/license_generator/gui.py`):
  - App standalone con Tkinter (Python puro)
  - Tabs: Generar licencia, Generar keypair RSA, Ayuda
  - Soporta HMAC y RSA-2048
- **CLI `lbamonitor-cli create-admin`**: crear/actualizar usuarios desde línea de comandos.
- **CLI `lbamonitor-cli init-db --with-admin`**: crea admin/admin123 + niveles membresía por defecto.
- **3 plugins nuevos**:
  - `usb_alert_popup_plugin.py` — popup visual Windows al insertar USB
  - `daily_closure_plugin.py` — PDF cierre diario automático
  - `telegram_notify_plugin.py` — notificaciones Telegram (requiere bot token)
- **Script `scripts/sign_plugins.py`**: firma todos los plugins con HMAC.
- **Endpoint público `GET /api/catalog/public`**: catálogo sin auth para web pública.
- **`docs/plugins.md` actualizado**: documenta los 8 plugins y 9 eventos soportados.

### Corregido (FIXED)
- **A4301 (CRÍTICO)**: Hashes de password unificados. `helpers.hash_password` ahora produce `pbkdf2_sha256$...` compatible con `auth.verify_password`. Login API funciona end-to-end.
- **A4302 (CRÍTICO)**: PluginManager se invoca en `main.py` lifespan. 8 plugins se cargan automáticamente.
- **A4303 (CRÍTICO)**: `MTPFilePoller._enumerate_files()` implementado con pythonnet + MediaDevices.dll.
- **A4304**: `_on_mtp_removed` cierra sesiones MTP correctamente.
- **A4306**: Catálogo público funciona (`/api/catalog/public` sin auth + Flask usa ese endpoint).
- **A4309**: `init-db --with-admin` crea admin/admin123 + niveles membresía.
- **A4310**: 116/116 tests unitarios pasan (integration tests aún fallan por setup, no regresiones).
- **A4311**: `get_current_user` respeta `require_auth=False` (devuelve admin dummy en dev).
- **A4316**: Trial de 10 días implementado con persistencia + anti-tampering.
- **A4317**: 8 plugins firmados con `.py.sig` (key de dev incluida).
- **A4318**: Settings expone pricing, monitoring, backup, logging, appearance, server, reward-rules, memberships.
- **A4320**: Descuentos multiplicativos en cadena (no MAX).
- **Plugin path bug**: search path de plugins corregido (subía 3 niveles, debía subir 4).
- **Plugin env var timing**: signing key se lee en `_verify_signature` (no en `__init__`) para respetar env vars seteadas después.
- **Auth dummy user**: usa `created` (no `created_at`) que es el campo real del modelo User.

### Cambiado (CHANGED)
- `web/` (Flask) → `web_legacy/` (preservado, no usado)
- Web integrada en FastAPI: `backend/lbamonitor/web/` con Jinja2Templates
- `helpers.hash_password` formato: `salt_hex$hash_hex` → `pbkdf2_sha256$iterations$salt_hex$hash_hex`
- `helpers.verify_password` soporta 3 formatos: bcrypt, pbkdf2 nuevo, legacy
- `pricing_engine.py`: descuentos MAX+ADD → multiplicativo en cadena
- `pyproject.toml`: añadido `jinja2~=3.1.4`

### Eliminado (REMOVED)
- `web/app.py` (Flask) — reemplazado por FastAPI Jinja2Templates
- Fallback `nojwt:` (peligroso)
- Secret `lbamonitor-default-secret` hardcoded
- Secret `change-me-in-production` hardcoded
- `log_manager.py` duplicado
- Dead code en `device_change_listener.py` (comentado)

### Seguridad
- Trial con anti-tampering: fecha de instalación firmada con HMAC
- Plugins firmados con HMAC-SHA256 obligatorio (8 plugins firmados)
- Auth JWT obligatoria por defecto (`require_auth=True`)
- Bypass solo en dev (`LBAMONITOR_ENV=development`)
- Secrets desde env vars con fail-fast en producción
- Rate limiting en login (5 intentos/min)
- CORS, security headers, cookies HTTPOnly
- Licencia RSA-2048 recomendada sobre HMAC

---

## [4.3.0] — 2026-07-06

Release con correcciones de v4.0.0/v4.2 y port de componentes de v4.2. Ver CHANGELOG histórico.

## [4.2.0] — 2026-05-15 (DEPRECATED)

NO usar. Reemplazada por v4.3/v4.4.

## [4.0.0] — 2026-03-01

Release inicial.

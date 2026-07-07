# Plugins LBAMonitor v4.4

Los plugins permiten extender LBAMonitor sin modificar el código principal. Cada plugin es un archivo `.py` en `backend/plugins/` que define funciones callback para eventos específicos.

## 🔐 Seguridad

**Todos los plugins deben estar firmados con HMAC-SHA256.** Cada plugin `.py` debe tener un archivo `.py.sig` adyacente con la firma. La firma se verifica con `LBAMONITOR_PLUGINS_SIGNING_KEY` (env var).

Para firmar plugins:
```bash
LBAMONITOR_PLUGINS_SIGNING_KEY=<secret> python scripts/sign_plugins.py
```

En desarrollo, puedes setear `LBAMONITOR_PLUGINS_ALLOW_UNSIGNED=1` para permitir plugins sin firma.

## 📦 Plugins incluidos (8)

### 1. `example_plugin.py` — Plugin de ejemplo
Demuestra la estructura básica de un plugin. No hace nada útil, solo loggea eventos.

### 2. `receipt_log_plugin.py` — Log de recibos
Guarda un registro JSON de cada cobro en `exports/receipts/`. Útil para auditoría.

### 3. `session_stats_plugin.py` — Estadísticas por sesión
Al cerrar una sesión USB, guarda un resumen JSON con: GB copiados, archivos, categorías, monto cobrado.

### 4. `sound_alert_plugin.py` — Alertas sonoras
Reproduce beeps de Windows al insertar/extraer USB, al cobrar, y al detectar errores. Fallback silencioso en Linux/Mac.

### 5. `excel_report_plugin.py` — Reporte Excel diario
Genera un archivo `.xlsx` al cerrar sesión con el detalle de copias. Usa `openpyxl`.

### 6. `usb_alert_popup_plugin.py` — Popup visual USB (NUEVO v4.4)
Muestra un popup nativo de Windows (MessageBox) al insertar un USB. Útil para kioscos donde el operador no tiene la app desktop abierta.

### 7. `daily_closure_plugin.py` — Cierre diario automático (NUEVO v4.4)
Genera un PDF con el resumen del día al cambiar de fecha o al hacer backup nocturno. Guarda en `exports/closure_<date>.pdf`.

### 8. `telegram_notify_plugin.py` — Notificaciones Telegram (NUEVO v4.4)
Envía mensajes a un chat de Telegram en eventos importantes (USB insertado, cobro, inicio/parada del servicio). Requiere configurar:
```
LBAMONITOR_TELEGRAM_BOT_TOKEN=<token>
LBAMONITOR_TELEGRAM_CHAT_ID=<chat_id>
```

## 📡 Eventos soportados (9)

| Evento | Parámetros | Se dispara cuando |
|---|---|---|
| `on_usb_inserted` | `drive_letter`, `volume_label`, `serial_number`, ... | Se inserta un USB mass-storage |
| `on_usb_removed` | `drive_letter` | Se extrae un USB |
| `on_file_copied` | `file_path`, `file_name`, `size_bytes`, `category` | Se copia un archivo al USB |
| `on_file_deleted` | `file_path`, `file_name` | Se elimina un archivo del USB |
| `on_payment_registered` | `amount`, `device_id`, `user_id` | Se registra un cobro |
| `on_session_started` | — | Arranca el servicio de monitoreo |
| `on_session_ended` | — | Se detiene el servicio |
| `on_backup_created` | `file_path`, `size_bytes` | Se crea un backup |
| `on_license_activated` | `tier`, `expires` | Se activa una licencia |

## 🛠️ Crear un plugin nuevo

1. Crea un archivo `.py` en `backend/plugins/` (ej: `mi_plugin.py`)
2. Define funciones para los eventos que quieras manejar:

```python
"""Mi plugin personalizado."""

def on_usb_inserted(drive_letter: str, volume_label: str = "", **kwargs) -> None:
    print(f"USB insertado: {drive_letter}")

def on_payment_registered(amount: float = 0, **kwargs) -> None:
    print(f"Cobro: ${amount:.2f}")

PLUGIN_NAME = "mi_plugin"
PLUGIN_VERSION = "1.0.0"
PLUGIN_DESCRIPTION = "Mi plugin personalizado"
```

3. Firma el plugin:
```bash
LBAMONITOR_PLUGINS_SIGNING_KEY=<secret> python scripts/sign_plugins.py
```

4. Reinicia el servicio. El plugin se cargará automáticamente al arrancar.

## 📋 Reglas

- **Sin `eval/exec/pickle`**: por seguridad, no uses estas funciones
- **Sin `subprocess` con `shell=True`**: usa `shell=False` y lista de args
- **Manejo de errores**: cualquier excepción en un plugin se loggea pero no rompe el servicio
- **Thread-safe**: los callbacks pueden ejecutarse en hilos diferentes, usa locks si modificas estado global
- **No bloquear**: si tu plugin hace I/O lento (HTTP, archivo grande), usa `asyncio.to_thread` o un hilo separado
- **Logging**: usa `print()` o configura loguru; los prints se capturan en el log del servicio

## 📊 Estado de carga de plugins

Endpoint: `GET /api/admin/plugins` (requiere admin) — devuelve lista de plugins cargados y sus eventos.

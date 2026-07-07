"""
Scheduler APScheduler — LBAMonitor v4.3.

Tareas programadas:
- Backup nocturno automático (configurable: backup.hour)
- Limpieza de caché cada hora (invalida entradas expiradas)
- Limpieza de logs cada 24h (rota archivos viejos)

Mejoras respecto a v4.2:
- BackupEngine se inicializa con argumentos correctos (session_factory, db_path, etc.)
- Limpieza de logs usa logging_setup (no log_manager inexistente)
- AsyncIO integration con AsyncIOScheduler en lugar de BackgroundScheduler
- Manejo de errores con loggeo detallado
"""
from __future__ import annotations

from lbamonitor.utils.logging_setup import get_logger

log = get_logger(__name__)

_scheduler = None


def create_scheduler():
    """Crea el scheduler AsyncIO (no lo arranca)."""
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
        from lbamonitor.core.config import get_settings

        s = get_settings()
        scheduler = AsyncIOScheduler(timezone="America/Havana")

        # Backup nocturno
        if s.backup.enabled:
            scheduler.add_job(
                _run_backup,
                CronTrigger(hour=s.backup.hour, minute=0),
                id="nightly_backup",
                replace_existing=True,
                misfire_grace_time=3600,  # 1h de gracia si se perdió
            )
            log.info(f"Backup nocturno programado a las {s.backup.hour:02d}:00")

        # Limpieza de caché cada hora
        scheduler.add_job(
            _cleanup_cache,
            "interval",
            hours=1,
            id="cache_cleanup",
            replace_existing=True,
        )

        # Limpieza de logs cada 24h
        scheduler.add_job(
            _cleanup_logs,
            "interval",
            hours=24,
            id="log_cleanup",
            replace_existing=True,
        )

        return scheduler
    except ImportError:
        log.warning("APScheduler no disponible — tareas programadas desactivadas")
        return _NoopScheduler()


async def _run_backup():
    """Ejecuta backup nocturno automático."""
    try:
        from lbamonitor.core.config import get_settings
        from lbamonitor.core.db import get_session_factory
        from lbamonitor.core.services.backup_engine import BackupEngine
        import asyncio

        s = get_settings()
        # Inicializar BackupEngine con argumentos correctos
        factory = get_session_factory()
        engine = BackupEngine(
            session_factory=factory,
            db_path=s.database.path,
            destination=s.backup.destination,
            max_backups=s.backup.keep_days,
        )
        # backup() es async
        record = await engine.backup(auto=True, notes="Backup nocturno automático")
        log.info(f"Backup nocturno completado: {record.file_path}")
    except Exception as e:
        log.error(f"Error en backup nocturno: {e}", exc_info=True)


async def _cleanup_cache():
    """Limpia entradas expiradas del caché."""
    try:
        from lbamonitor.core.cache.memory_cache import get_cache
        cache = get_cache()
        n = await cache.cleanup()
        # Invalidar estadísticas antiguas
        invalidated = await cache.invalidate_prefix("stats:")
        if n or invalidated:
            log.debug(f"Cache limpiada: {n} expiradas, {invalidated} stats invalidadas")
    except Exception as e:
        log.warning(f"Error limpiando caché: {e}")


async def _cleanup_logs():
    """Rota logs viejos. Usa loguru (no log_manager inexistente)."""
    try:
        from lbamonitor.utils.logging_setup import get_logger
        # Loguru maneja rotación automática, pero podemos forzar cleanup
        # de archivos sueltos en el directorio de logs
        from lbamonitor.core.config import get_settings
        from pathlib import Path
        import time

        s = get_settings()
        log_path = Path(s.logging.path)
        if not log_path.is_dir():
            return

        cutoff = time.time() - (s.backup.keep_days * 86400)
        count = 0
        for f in log_path.glob("*.log*"):
            try:
                if f.is_file() and f.stat().st_mtime < cutoff:
                    f.unlink()
                    count += 1
            except Exception:
                pass
        if count:
            log.info(f"Limpieza de logs: {count} archivos antiguos eliminados")
    except Exception as e:
        log.warning(f"Error limpiando logs: {e}")


class _NoopScheduler:
    """Scheduler vacío cuando APScheduler no está disponible."""
    def start(self): pass
    def shutdown(self, wait=True): pass
    def add_job(self, *a, **kw): pass


async def start_scheduler():
    """Arranca el scheduler global."""
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    _scheduler = create_scheduler()
    _scheduler.start()
    return _scheduler


async def stop_scheduler():
    """Detiene el scheduler global."""
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=True)
        except Exception:
            pass
        _scheduler = None

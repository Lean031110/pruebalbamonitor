"""
Servicio de monitoreo orquestador.

Arranca todos los componentes:
  - USBMonitor (WMI events para USB mass-storage)
  - MTPMonitor (pythonnet + MediaDevices.dll para celulares)
  - ClockMonitor (detecta cambios de reloj)
  - SessionHeartbeat (ServiceSession con heartbeat)
  - CopyMonitor por cada USB insertada (watchdog con debouncer)
  - PublicityCopier al insertar USB (asyncio.to_thread)
  - Auto-copia de PDF explicativo del servicio al USB (primera inserción)

CRÍTICO: Todas las operaciones bloqueantes (copia de archivos, generación
de imágenes Pillow, consultas WMI) se ejecutan con `asyncio.to_thread()`
para no congelar la detección de nuevos USB.
"""
from __future__ import annotations

import asyncio
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from lbamonitor.core.config import get_settings
from lbamonitor.core.db import get_session_factory
from lbamonitor.core.models import (
    Copy,
    Deletion,
    InsertedDrive,
    PCDatetimeChange,
    RemovedDrive,
    ServiceSession,
    USBDevice,
    USBSession,
)
from lbamonitor.core.services.pdf_engine import PdfEngine
from lbamonitor.monitor.clock_monitor import ClockMonitor
from lbamonitor.monitor.categorizer import is_system_file
from lbamonitor.monitor.file_watcher import CopyMonitor, FileEvent
from lbamonitor.monitor.mtp_monitor import MTPDeviceInfo, MTPMonitor
from lbamonitor.monitor.publicity_copier import copy_publicity_to_usb
from lbamonitor.monitor.session_heartbeat import SessionHeartbeat
from lbamonitor.monitor.usb_monitor import USBDeviceInfo, USBMonitor
from lbamonitor.monitor.wmi_utils import is_windows
from lbamonitor.utils.helpers import to_utc, utcnow
from lbamonitor.utils.logging_setup import get_logger

log = get_logger(__name__)


# Nombre del PDF explicativo del servicio que se auto-copia al USB.
SERVICE_PDF_FILENAME = "LBAMonitor_Servicio.pdf"


class MonitorService:
    """
    Orquestador del servicio de monitoreo.

    Ciclo de vida:
      1. start(): crea ServiceSession, arranca ClockMonitor, USBMonitor, MTPMonitor
      2. Al insertar USB: crea InsertedDrive, arranca CopyMonitor, copia publicidad
      3. Al extraer USB: cierra CopyMonitor, crea RemovedDrive, actualiza InsertedDrive
      4. stop(): detiene todo, cierra ServiceSession
    """

    def __init__(self) -> None:
        self._factory = None
        self._heartbeat: SessionHeartbeat | None = None
        self._clock: ClockMonitor | None = None
        self._usb_monitor: USBMonitor | None = None
        self._mtp_monitor: MTPMonitor | None = None
        # CopyMonitors activos: drive_letter → CopyMonitor
        self._active_watchers: dict[str, CopyMonitor] = {}
        # InsertedDrives activos: drive_letter → InsertedDrive (ORM)
        self._active_drives: dict[str, InsertedDrive] = {}
        self._running = False
        self._settings = get_settings()

    # -----------------------------------------------------------------
    # Ciclo de vida
    # -----------------------------------------------------------------

    async def start(self) -> None:
        """Arranca el servicio de monitoreo."""
        if self._running:
            log.warning("MonitorService ya está corriendo")
            return

        log.info("MonitorService arrancando...")
        self._factory = get_session_factory()
        self._settings = get_settings()

        # 1. Heartbeat de sesión
        self._heartbeat = SessionHeartbeat(
            self._factory, interval_seconds=300
        )
        await self._heartbeat.start()

        # 2. ClockMonitor (usar último heartbeat como baseline)
        last_alive = await self._heartbeat.get_last_alive()
        self._clock = ClockMonitor(threshold_seconds=60, interval_seconds=60)
        if last_alive:
            self._clock.initialize(last_known_time=last_alive)
            log.info(f"ClockMonitor inicializado con último heartbeat: {last_alive}")
        else:
            self._clock.initialize()
        self._clock.set_on_change_callback(self._on_clock_change)
        await self._clock.start()

        # 3. USBMonitor (solo Windows; en otros SO queda inactivo)
        if is_windows():
            self._usb_monitor = USBMonitor(
                on_inserted=self._on_usb_inserted,
                on_removed=self._on_usb_removed,
                poll_interval_seconds=2,
            )
            await self._usb_monitor.start()
        else:
            log.warning(
                "Monitor USB desactivado (solo Windows). "
                "El servicio queda en modo API-only."
            )

        # 4. MTPMonitor (solo Windows con pythonnet)
        self._mtp_monitor = MTPMonitor(
            on_inserted=self._on_mtp_inserted,
            on_removed=self._on_mtp_removed,
            poll_interval_seconds=self._settings.monitoring.mtp_poll_interval_seconds,
        )
        await self._mtp_monitor.start()

        self._running = True
        log.info("MonitorService arrancado ✓")

    async def stop(self) -> None:
        """Detiene el servicio."""
        if not self._running:
            return

        log.info("MonitorService deteniéndose...")
        self._running = False

        # Detener watchers activos
        for drive, watcher in list(self._active_watchers.items()):
            await self._finalize_drive(drive, force=True)

        # Detener monitores
        if self._mtp_monitor:
            await self._mtp_monitor.stop()
        if self._usb_monitor:
            await self._usb_monitor.stop()
        if self._clock:
            await self._clock.stop()
        if self._heartbeat:
            await self._heartbeat.stop()

        log.info("MonitorService detenido ✓")

    # -----------------------------------------------------------------
    # Callbacks USB
    # -----------------------------------------------------------------

    async def _on_usb_inserted(self, info: USBDeviceInfo) -> None:
        """Se dispara cuando una USB mass-storage es insertada."""
        log.info(f"Procesando inserción USB: {info.drive_letter}")

        try:
            async with self._factory() as session:
                # 1. Crear o recuperar USBDevice por fingerprint
                usb_device = await self._get_or_create_usb_device(session, info)

                # 2. Calcular PreviousInsertionsCounter y PreviousPaymentsSum
                prev_count, prev_sum = await self._compute_device_history(
                    session, info.fingerprint
                )

                # 3. Crear InsertedDrive
                drive = InsertedDrive(
                    insertion_date_time=utcnow(),
                    name=info.drive_letter,
                    root_directory=info.root_directory,
                    volume_label=info.volume_label,
                    serial_number=info.hardware_serial or info.volume_serial,
                    model=info.model,
                    space_bytes=info.total_capacity,
                    available_space_bytes=info.free_capacity,
                    is_mobile=False,
                    is_mounted_folder=False,
                    previous_insertions_counter=prev_count,
                    previous_payments_sum=prev_sum,
                    usb_device_id=usb_device.id if usb_device else None,
                )
                session.add(drive)
                await session.commit()
                await session.refresh(drive)
                self._active_drives[info.drive_letter] = drive

                log.info(
                    f"InsertedDrive #{drive.id} creado para {info.drive_letter} "
                    f"(fingerprint={info.fingerprint[:16]}... prev_count={prev_count})"
                )

            # 4. Arrancar CopyMonitor (watchdog) en background
            watcher = CopyMonitor(
                callback=lambda ev, dl=info.drive_letter: self._on_file_event(dl, ev),
                debounce_ms=self._settings.monitoring.fs_debounce_ms,
                exclude_patterns=self._settings.monitoring.exclude_patterns,
                exclude_system=self._settings.monitoring.exclude_system_files,
            )
            watcher.start(info.root_directory or f"{info.drive_letter}\\")
            self._active_watchers[info.drive_letter] = watcher

            # 5. Copiar publicidad si está activado (en thread aparte)
            if (
                self._settings.paths.publicity_automatic
                and self._settings.paths.publicity_folder
            ):
                asyncio.create_task(
                    self._copy_publicity_safe(
                        info.drive_letter,
                        self._settings.paths.publicity_folder,
                    )
                )

            # 6. Auto-copia del PDF explicativo del servicio (en thread aparte)
            #    Solo si la USB NO lo tiene ya (para no sobrescribirlo cada vez).
            asyncio.create_task(
                self._ensure_service_pdf_on_usb(info.drive_letter)
            )

        except Exception as e:
            log.exception(f"Error procesando inserción USB {info.drive_letter}: {e}")

    async def _on_usb_removed(self, drive_letter: str) -> None:
        """Se dispara cuando una USB mass-storage es extraída."""
        log.info(f"Procesando extracción USB: {drive_letter}")
        await self._finalize_drive(drive_letter)

    async def _finalize_drive(self, drive_letter: str, force: bool = False) -> None:
        """Cierra el watcher, crea RemovedDrive y actualiza InsertedDrive."""
        # Detener CopyMonitor
        watcher = self._active_watchers.pop(drive_letter, None)
        if watcher:
            stats = watcher.finalize()
            watcher.stop()
            log.info(
                f"CopyMonitor de {drive_letter} finalizado: "
                f"{stats.get('files_copied', 0)} copiados, "
                f"{stats.get('files_deleted', 0)} borrados"
            )

        # Actualizar BD
        drive = self._active_drives.pop(drive_letter, None)
        if not drive:
            log.warning(f"No hay InsertedDrive activo para {drive_letter}")
            return

        try:
            async with self._factory() as session:
                # Crear RemovedDrive
                removed = RemovedDrive(
                    removal_date_time=utcnow(),
                    name=drive_letter,
                    root_directory=drive.root_directory,
                )
                session.add(removed)
                await session.flush()  # Para tener removed.id

                # Actualizar InsertedDrive
                drive.removed_drive_id = removed.id
                # Actualizar espacio libre al final (si podemos leerlo)
                # — ya no podemos porque la USB fue extraída, dejamos None
                await session.commit()

                log.info(
                    f"InsertedDrive #{drive.id} cerrado, RemovedDrive #{removed.id} creado"
                )
        except Exception as e:
            log.exception(f"Error finalizando drive {drive_letter}: {e}")

    # -----------------------------------------------------------------
    # Callbacks MTP (similar a USB pero sin watchdog)
    # -----------------------------------------------------------------

    async def _on_mtp_inserted(self, info: MTPDeviceInfo) -> None:
        """Se dispara cuando un dispositivo MTP (celular) es insertado."""
        log.info(f"Procesando inserción MTP: {info.name} ({info.model})")
        try:
            async with self._factory() as session:
                # Para MTP, IsMobile=True y no hay drive_letter
                # El fingerprint se basa en model + serial
                prev_count, prev_sum = await self._compute_device_history(
                    session, info.fingerprint
                )

                drive = InsertedDrive(
                    insertion_date_time=utcnow(),
                    name=info.name,
                    root_directory="",  # MTP no tiene ruta de filesystem
                    volume_label=info.friendly_name,
                    serial_number=info.serial_number,
                    model=info.model,
                    space_bytes=info.total_capacity,
                    available_space_bytes=info.free_capacity,
                    is_mobile=True,
                    is_mounted_folder=False,
                    previous_insertions_counter=prev_count,
                    previous_payments_sum=prev_sum,
                )
                session.add(drive)
                await session.commit()
                await session.refresh(drive)

                # MTP no se puede meter en _active_drives (no hay drive_letter)
                # Lo guardamos en un dict aparte si hace falta
                log.info(
                    f"InsertedDrive #{drive.id} creado para MTP {info.name} "
                    f"(fingerprint={info.fingerprint[:16]}...)"
                )

            # NOTA: Para MTP, no podemos usar watchdog. El polling de archivos
            # MTP se implementará en una fase posterior (requiere más trabajo
            # con la API de MediaDevices.dll).
        except Exception as e:
            log.exception(f"Error procesando inserción MTP {info.name}: {e}")

    async def _on_mtp_removed(self, device_id: str) -> None:
        """Se dispara cuando un dispositivo MTP es extraído."""
        log.info(f"Procesando extracción MTP: {device_id}")
        # TODO: Marcar el InsertedDrive correspondiente como cerrado
        # Por ahora solo loggeamos — se completará cuando integremos
        # el polling de archivos MTP.

    # -----------------------------------------------------------------
    # Callback de eventos de archivo
    # -----------------------------------------------------------------

    async def _on_file_event(self, drive_letter: str, event: FileEvent) -> None:
        """
        Se dispara cuando watchdog detecta un cambio en una USB montada.

        Crea registros Copy o Deletion según el tipo de evento.
        """
        drive = self._active_drives.get(drive_letter)
        if not drive:
            log.warning(f"Evento de archivo en {drive_letter} sin InsertedDrive activo")
            return

        try:
            async with self._factory() as session:
                if event.operation.value == "created":
                    copy = Copy(
                        copy_date_time=event.detected_at,
                        full_path=event.file_path,
                        extension=event.file_ext,
                        file_name=event.file_name,
                        size_bytes=event.file_size,
                        inserted_drive_id=drive.id,
                        category=event.category,
                    )
                    session.add(copy)
                    log.debug(
                        f"Copy creado: {event.file_name} ({event.file_size} bytes) "
                        f"en {drive_letter}"
                    )
                elif event.operation.value == "deleted":
                    deletion = Deletion(
                        deletion_date_time=event.detected_at,
                        full_path=event.file_path,
                        extension=event.file_ext,
                        file_name=event.file_name,
                        inserted_drive_id=drive.id,
                    )
                    session.add(deletion)
                    log.debug(f"Deletion creada: {event.file_name} en {drive_letter}")

                await session.commit()
        except Exception as e:
            log.exception(f"Error guardando evento de archivo en {drive_letter}: {e}")

    # -----------------------------------------------------------------
    # Callback de cambio de reloj
    # -----------------------------------------------------------------

    async def _on_clock_change(self, moment: datetime, new_time: datetime) -> None:
        """Se dispara cuando ClockMonitor detecta un cambio de reloj."""
        try:
            async with self._factory() as session:
                change = PCDatetimeChange(
                    moment=to_utc(moment),
                    to=to_utc(new_time),
                )
                session.add(change)
                await session.commit()
                log.warning(
                    f"PCDatetimeChange registrado: "
                    f"moment={moment.isoformat()} → {new_time.isoformat()}"
                )
        except Exception as e:
            log.exception(f"Error guardando cambio de reloj: {e}")

    # -----------------------------------------------------------------
    # Helpers de BD
    # -----------------------------------------------------------------

    async def _get_or_create_usb_device(
        self,
        session: AsyncSession,
        info: USBDeviceInfo,
    ) -> USBDevice | None:
        """Recupera o crea un USBDevice por fingerprint."""
        if not info.fingerprint:
            return None

        # Buscar por serial_number (que es el fingerprint normalizado)
        # En nuestra DB, serial_number guarda el fingerprint compuesto
        result = await session.execute(
            select(USBDevice).where(USBDevice.serial_number == info.fingerprint).limit(1)
        )
        device = result.scalar_one_or_none()

        if device:
            # Actualizar last_seen y visit_count
            device.last_seen = utcnow()
            device.visit_count = (device.visit_count or 0) + 1
            device.is_known = True
            await session.flush()
            return device

        # Crear nuevo
        device = USBDevice(
            serial_number=info.fingerprint,
            name=info.volume_label or info.drive_letter,
            brand=info.manufacturer,
            manufacturer=info.manufacturer,
            model=info.model,
            vid=info.vid,
            pid=info.pid,
            total_capacity=info.total_capacity,
            connection_type=info.connection_type,
            first_seen=utcnow(),
            last_seen=utcnow(),
            visit_count=1,
            is_known=True,
        )
        session.add(device)
        await session.flush()
        return device

    async def _compute_device_history(
        self,
        session: AsyncSession,
        fingerprint: str,
    ) -> tuple[int, int]:
        """
        Calcula PreviousInsertionsCounter y PreviousPaymentsSum para un
        dispositivo identificado por fingerprint.

        Busca todas las inserciones anteriores con el mismo serial_number
        (que guarda el fingerprint).
        """
        if not fingerprint:
            return 0, 0

        try:
            # Contar inserciones anteriores
            count_result = await session.execute(
                select(func.count())
                .select_from(InsertedDrive)
                .where(InsertedDrive.serial_number == fingerprint)
            )
            prev_count = count_result.scalar() or 0

            # Sumar pagos anteriores
            sum_result = await session.execute(
                select(func.coalesce(func.sum(InsertedDrive.payment), 0))
                .where(InsertedDrive.serial_number == fingerprint)
            )
            prev_sum = sum_result.scalar() or 0

            return int(prev_count), int(prev_sum)
        except Exception as e:
            log.warning(f"Error calculando historial del dispositivo: {e}")
            return 0, 0

    async def _copy_publicity_safe(self, drive_letter: str, source_folder: str) -> None:
        """Wrapper seguro para copiar publicidad (captura errores)."""
        try:
            result = await copy_publicity_to_usb(drive_letter, source_folder)
            if result["failed_count"] > 0:
                log.warning(
                    f"Copia de publicidad con errores: "
                    f"{result['failed_count']} archivos fallidos"
                )
        except Exception as e:
            log.exception(f"Error copiando publicidad a {drive_letter}: {e}")

    async def _ensure_service_pdf_on_usb(self, drive_letter: str) -> None:
        """
        Auto-copia el PDF explicativo del servicio al USB si no lo tiene.

        Comportamiento:
          - Verifica si existe `<drive>:\\LBAMonitor_Servicio.pdf` en la raíz.
          - Si NO existe, lo genera con `PdfEngine.generate_service_pdf()` en
            un directorio temporal y lo copia al USB.
          - Todo se hace en un hilo (asyncio.to_thread) para no bloquear el
            event loop (la generación del PDF puede tardar 1-3 segundos).
          - Si el USB se extrajo mientras se generaba, el error se captura
            silenciosamente.
        """
        try:
            # Normalizar ruta raíz del USB
            root_str = drive_letter.replace("\\", "/").rstrip("/")
            if not root_str:
                log.warning("Drive letter vacío, no se puede copiar PDF servicio")
                return
            # En Windows usamos "\\" como separador; en Linux/Mac "/"
            if is_windows():
                root = Path(f"{root_str}\\")
            else:
                root = Path(root_str)
            target = root / SERVICE_PDF_FILENAME

            # Verificar si ya existe (en hilo para no bloquear)
            already_has = await asyncio.to_thread(
                lambda: target.is_file() and target.stat().st_size > 0
            )
            if already_has:
                log.debug(
                    f"USB {drive_letter} ya tiene {SERVICE_PDF_FILENAME} "
                    f"(no se sobrescribe)"
                )
                return

            # Generar PDF en directorio temporal, luego copiar
            # (reportlab escribe síncrono y bloqueante → to_thread)
            def _generate_and_copy() -> Path | None:
                try:
                    import tempfile
                    with tempfile.TemporaryDirectory(
                        prefix="lbamonitor-pdf-"
                    ) as tmp:
                        tmp_pdf = Path(tmp) / SERVICE_PDF_FILENAME
                        PdfEngine.generate_service_pdf(
                            business_info=self._settings.business,
                            output_path=tmp_pdf,
                        )
                        # Verificar que el USB sigue montado
                        if not root.is_dir():
                            log.warning(
                                f"USB {drive_letter} extraído mientras se "
                                f"generaba el PDF servicio"
                            )
                            return None
                        shutil.copy2(tmp_pdf, target)
                        return target
                except Exception as e:
                    log.warning(
                        f"Error generando/copiando PDF servicio a "
                        f"{drive_letter}: {e}"
                    )
                    return None

            result_path = await asyncio.to_thread(_generate_and_copy)
            if result_path:
                log.info(
                    f"PDF servicio copiado a USB {drive_letter}: {result_path} "
                    f"({result_path.stat().st_size} bytes)"
                )
        except Exception as e:
            log.warning(
                f"No se pudo auto-copiar PDF servicio a {drive_letter}: {e}"
            )

    # -----------------------------------------------------------------
    # Status / info
    # -----------------------------------------------------------------

    def get_status(self) -> dict:
        """Devuelve el estado actual del servicio para /api/health."""
        return {
            "running": self._running,
            "is_windows": is_windows(),
            "active_usb_drives": list(self._active_drives.keys()),
            "active_watchers": list(self._active_watchers.keys()),
            "session_id": self._heartbeat.session_id if self._heartbeat else None,
            "session_start": (
                self._heartbeat.start_time.isoformat()
                if self._heartbeat and self._heartbeat.start_time
                else None
            ),
            "mtp_available": (
                self._mtp_monitor._available if self._mtp_monitor else False
            ),
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_monitor_service: MonitorService | None = None


async def start_monitor_service() -> MonitorService:
    """Arranca el servicio de monitoreo global."""
    global _monitor_service
    if _monitor_service is None:
        _monitor_service = MonitorService()
    await _monitor_service.start()
    return _monitor_service


async def stop_monitor_service() -> None:
    """Detiene el servicio de monitoreo global."""
    global _monitor_service
    if _monitor_service is not None:
        await _monitor_service.stop()
        _monitor_service = None


def get_monitor_service() -> MonitorService | None:
    """Devuelve la instancia activa del servicio (o None)."""
    return _monitor_service


# Aliases cortos para uso en lifespan de la API
async def start_monitor() -> MonitorService:
    """Alias de start_monitor_service para usar en main.py lifespan."""
    return await start_monitor_service()


async def stop_monitor() -> None:
    """Alias de stop_monitor_service para usar en main.py lifespan."""
    await stop_monitor_service()

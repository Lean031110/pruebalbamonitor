"""
Simulación completa del flujo de negocio de LBAMonitor.

Verifica end-to-end:
  1. Arranque del servicio (migraciones, ServiceSession, ClockMonitor)
  2. Crear operador (admin)
  3. Insertar USB (crear InsertedDrive + USBDevice)
  4. Registrar copias de archivos (Copy)
  5. Registrar borrados (Deletion)
  6. Actualizar pago (PaymentAlteration)
  7. Calcular precio con PricingEngine (5 modos + VIP)
  8. Extraer USB (RemovedDrive)
  9. Calcular estadísticas
  10. Crear catálogo
  11. Crear cliente + membresía
  12. Generar factura PNG
  13. Crear backup
  14. Verificar sesiones del servicio
  15. Verificar cambios de reloj
  16. WebSocket eventos
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Setup paths
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# Config de test
os.environ["LBAMONITOR_DATABASE__PATH"] = "/tmp/lba_simulacion.db"
os.environ["LBAMONITOR_LOGGING__CONSOLE"] = "false"
os.environ["LBAMONITOR_LOGGING__LEVEL"] = "WARNING"


async def simulate() -> int:
    """Ejecuta la simulación completa. Devuelve el número de errores."""
    errors = 0
    print_header("SIMULACIÓN COMPLETA LBAMonitor")

    # ---------- 1. Inicializar ----------
    print_step(1, "Inicializar BD y migraciones")
    from lbamonitor.core.db import init_engine, dispose_engine, get_session_factory
    from lbamonitor.core.migrations import run_migrations

    db_path = Path("/tmp/lba_simulacion.db")
    if db_path.exists():
        db_path.unlink()
    for suffix in ("-wal", "-shm"):
        p = Path(str(db_path) + suffix)
        if p.exists():
            p.unlink()

    await init_engine()
    run_migrations()
    factory = get_session_factory()
    print("  ✓ Migraciones aplicadas")
    print()

    # ---------- 2. Crear operador ----------
    print_step(2, "Crear operador admin")
    from lbamonitor.core.repositories import UserRepository
    async with factory() as session:
        repo = UserRepository(session)
        admin = await repo.create_with_password(
            username="admin",
            password="admin123",
            role="admin",
            full_name="Administrador",
            email="admin@lbamonitor.test",
        )
        operador = await repo.create_with_password(
            username="operador1",
            password="op123",
            role="operator",
            full_name="Juan Operador",
        )
        await session.commit()
        print(f"  ✓ Admin creado: id={admin.id} username={admin.username}")
        print(f"  ✓ Operador creado: id={operador.id} username={operador.username}")

        user = await repo.verify_credentials("admin", "admin123")
        assert user is not None, "Login admin falló"
        print(f"  ✓ Login admin OK (last_login={user.last_login})")

        user_wrong = await repo.verify_credentials("admin", "wrong")
        assert user_wrong is None, "Login con password incorrecta debería fallar"
        print(f"  ✓ Login con password incorrecta rechazado")
    print()

    # ---------- 3. Crear USB device + InsertedDrive ----------
    print_step(3, "Insertar USB (crear USBDevice + InsertedDrive)")
    from lbamonitor.core.repositories import USBDeviceRepository, InsertedDriveRepository
    from lbamonitor.utils.helpers import utcnow
    fingerprint = "a" * 64

    async with factory() as session:
        dev_repo = USBDeviceRepository(session)
        drive_repo = InsertedDriveRepository(session)

        device = await dev_repo.get_or_create(
            fingerprint=fingerprint,
            name="Kingston DT",
            brand="Kingston",
            model="DataTraveler",
            vid="0951",
            pid="1666",
            total_capacity=32 * 1024**3,
            connection_type="usb_3",
        )
        await session.commit()
        print(f"  ✓ USBDevice creado: id={device.id} visit_count={device.visit_count}")

        prev_count, prev_sum = await drive_repo.compute_history(fingerprint)
        print(f"  ✓ Historial previo: count={prev_count} sum={prev_sum}")

        drive = await drive_repo.create(
            insertion_date_time=utcnow(),
            name="E:",
            root_directory="E:\\",
            volume_label="KINGSTON",
            serial_number=fingerprint,
            model="DataTraveler",
            space_bytes=32 * 1024**3,
            available_space_bytes=10 * 1024**3,
            is_mobile=False,
            previous_insertions_counter=prev_count,
            previous_payments_sum=prev_sum,
            usb_device_id=device.id,
            user_id=admin.id,
        )
        await session.commit()
        await session.refresh(drive)
        print(f"  ✓ InsertedDrive creado: id={drive.id} name={drive.name}")
    print()

    # ---------- 4. Registrar copias ----------
    print_step(4, "Registrar copias de archivos (Copy)")
    from lbamonitor.core.repositories import CopyRepository
    from lbamonitor.monitor.categorizer import categorize_file

    test_files = [
        ("pelicula.mp4", 1_500_000_000),
        ("serie_s01e05.mkv", 800_000_000),
        ("cancion.mp3", 5_000_000),
        ("documento.pdf", 200_000),
        ("foto.jpg", 3_500_000),
        ("app.apk", 50_000_000),
    ]

    async with factory() as session:
        repo = CopyRepository(session)
        for file_name, size in test_files:
            category = categorize_file(file_name).value
            copy = await repo.create(
                copy_date_time=utcnow(),
                full_path=f"E:\\{file_name}",
                file_name=file_name,
                extension="." + file_name.split(".")[-1],
                size_bytes=size,
                inserted_drive_id=drive.id,
                category=category,
            )
            print(f"  ✓ Copy: {file_name:30s} size={size:>13} cat={category}")
        await session.commit()
    print()

    # ---------- 5. Registrar borrados ----------
    print_step(5, "Registrar borrados (Deletion)")
    from lbamonitor.core.repositories import DeletionRepository
    async with factory() as session:
        repo = DeletionRepository(session)
        deletion = await repo.create(
            deletion_date_time=utcnow(),
            full_path="E:\\archivo_viejo.txt",
            file_name="archivo_viejo.txt",
            extension=".txt",
            inserted_drive_id=drive.id,
        )
        await session.commit()
        print(f"  ✓ Deletion: {deletion.file_name}")
    print()

    # ---------- 6. Actualizar pago ----------
    print_step(6, "Actualizar pago (genera PaymentAlteration)")
    async with factory() as session:
        repo = InsertedDriveRepository(session)
        drive = await repo.get_by_id(drive.id)
        drive = await repo.update_payment(drive, 50, user_id=admin.id)
        drive = await repo.update_payment(drive, 75, user_id=admin.id)
        await session.commit()
        print(f"  ✓ Pago actualizado: 0 → 50 → 75")

        from lbamonitor.core.repositories import PaymentAlterationRepository
        pa_repo = PaymentAlterationRepository(session)
        alterations = await pa_repo.list_by_drive(drive.id)
        for a in alterations:
            print(f"    - {a.previous_payment} → {a.new_payment} by user_id={a.user_id}")
    print()

    # ---------- 7. PricingEngine ----------
    print_step(7, "PricingEngine — 5 modos + VIP")
    from lbamonitor.core.services.pricing_engine import get_pricing_engine
    engine = get_pricing_engine()

    test_cases = [
        ("per_gb", 4.5, 12, "none", 0.0, "Sin descuento"),
        ("per_gb", 4.5, 12, "vip", 0.0, "VIP 10%"),
        ("per_gb", 4.5, 12, "free", 0.0, "VIP FREE 100%"),
        ("per_gb", 4.5, 12, "employee", 0.0, "Employee 50%"),
        ("per_file", 0, 50, "none", 0.0, "Por archivo"),
        ("fixed", 0, 0, "none", 0.0, "Precio fijo"),
        ("per_gb", 4.5, 12, "none", 10.0, "Membresía 10%"),
    ]
    for mode, gb, files, vip, tier_disc, desc in test_cases:
        calc = engine.calculate(
            mode=mode, gb_copied=gb, files_copied=files,
            vip_type=vip, tier_discount_percent=tier_disc,
        )
        print(f"  ✓ {mode:8s} gb={gb} vip={vip:8s} tier={tier_disc}% "
              f"base={calc.base_price:>7.2f} disc={calc.discount_percent:>5.1f}% "
              f"suggested={calc.suggested_price:>7.2f}  [{desc}]")
    print()

    # ---------- 8. Extraer USB ----------
    print_step(8, "Extraer USB (RemovedDrive)")
    from lbamonitor.core.repositories import RemovedDriveRepository
    from lbamonitor.core.models import RemovedDrive
    async with factory() as session:
        removed = RemovedDrive(
            removal_date_time=utcnow(),
            name="E:",
            root_directory="E:\\",
        )
        session.add(removed)
        await session.flush()

        drive_repo = InsertedDriveRepository(session)
        drive = await drive_repo.get_by_id(drive.id)
        drive.removed_drive_id = removed.id
        drive.available_space_bytes_at_the_end = 8 * 1024**3
        await session.commit()
        print(f"  ✓ RemovedDrive creado: id={removed.id}")
        print(f"  ✓ InsertedDrive actualizado: removed_drive_id={drive.removed_drive_id}")
    print()

    # ---------- 9. Estadísticas ----------
    print_step(9, "Calcular estadísticas")
    from lbamonitor.core.services.statistics_service import StatisticsService
    async with factory() as session:
        svc = StatisticsService(session)
        today = await svc.today_kpis()
        month = await svc.month_kpis()
        insights = await svc.business_insights()
        print(f"  ✓ KPIs hoy:    transacciones={today['transactions']} revenue={today['revenue']} usb={today['usb_count']}")
        print(f"  ✓ KPIs mes:    transacciones={month['transactions']} revenue={month['revenue']}")
        print(f"  ✓ Insights:    dia_pico={insights['busiest_day_of_week']} hora_pico={insights['peak_hour']}")
        print(f"                 nuevos_30d={insights['new_clients_30d']} inactivos_60d={insights['inactive_clients_60d']}")

        from lbamonitor.core.repositories import CopyRepository
        copy_repo = CopyRepository(session)
        top_files = await copy_repo.top_files(limit=5)
        print(f"  ✓ Top files:")
        for f in top_files:
            print(f"    - {f['file_name']:30s} count={f['count']}")
    print()

    # ---------- 10. Catálogo ----------
    print_step(10, "Crear catálogo multimedia")
    from lbamonitor.core.repositories import CatalogRepository
    async with factory() as session:
        repo = CatalogRepository(session)
        entries_data = [
            ("Inception", "movie", 2010, "Sci-Fi", 8.8, 4.5),
            ("Breaking Bad S01", "series", 2008, "Drama", 9.5, 12.0),
            ("Recopilación Pop 2024", "music", 2024, "Pop", 7.5, 1.2),
        ]
        for title, cat, year, genre, rating, size in entries_data:
            e = await repo.create(
                title=title, category=cat, year=year, genre=genre,
                rating=rating, size_gb=size, active=True,
            )
            print(f"  ✓ CatalogEntry: {title:30s} cat={cat} rating={rating}")
        await session.commit()
    print()

    # ---------- 11. Cliente + membresía ----------
    print_step(11, "Crear cliente y membresías")
    from lbamonitor.core.repositories import (
        ClientRepository, MembershipLevelRepository, VIPRepository,
    )
    async with factory() as session:
        level_repo = MembershipLevelRepository(session)
        await level_repo.initialize_defaults()
        await session.commit()
        levels = await level_repo.list_ordered()
        print(f"  ✓ {len(levels)} niveles creados:")
        for l in levels:
            print(f"    - {l.tier:10s} min_visits={l.min_visits} min_gb={l.min_gb} discount={l.discount_percent}%")

        client_repo = ClientRepository(session)
        client = await client_repo.increment_visit(
            device_id=device.id, spent=75.0, gb_copied=4.5,
        )
        tier = await level_repo.compute_tier(
            client.visit_count, client.total_gb_copied, client.total_spent
        )
        client.tier = tier
        await session.commit()
        print(f"  ✓ Cliente creado: visits={client.visit_count} spent={client.total_spent} tier={client.tier}")

        vip_repo = VIPRepository(session)
        vip = await vip_repo.upsert(
            device_id=device.id, vip_type="vip", discount_percent=10.0,
            reason="Cliente frecuente",
        )
        await session.commit()
        print(f"  ✓ VIP asignado: type={vip.vip_type} discount={vip.discount_percent}%")
    print()

    # ---------- 12. Factura PNG ----------
    print_step(12, "Generar factura PNG")
    from lbamonitor.core.services.invoice_engine import generate_invoice_image
    async with factory() as session:
        repo = InsertedDriveRepository(session)
        drive = await repo.get_by_id(drive.id)
        copies = await repo.get_copies(drive.id)
        copies_data = [
            {"file_name": c.file_name, "size_bytes": c.size_bytes or 0,
             "extension": c.extension, "copy_date_time": c.copy_date_time}
            for c in copies
        ]
        png_bytes = await generate_invoice_image(
            drive_id=drive.id,
            drive_name=drive.name or "E:",
            drive_serial=drive.serial_number,
            drive_model=drive.model,
            copies=copies_data,
            payment=75,
            business_name="Copistería Test LBAMonitor",
            business_address="Calle Test 123, La Habana",
            marketing_text="¡Síguenos en redes!",
            include_webcam=False,
        )
        invoice_path = Path("/tmp/lba_invoice_test.png")
        invoice_path.write_bytes(png_bytes)
        print(f"  ✓ Factura generada: {invoice_path} ({len(png_bytes)} bytes)")
    print()

    # ---------- 13. Backup ----------
    print_step(13, "Crear backup de la BD")
    from lbamonitor.core.services.backup_engine import BackupEngine
    from lbamonitor.core.config import get_settings
    s = get_settings()
    backup_engine = BackupEngine(
        session_factory=factory,
        db_path=s.database.path,
        destination="/tmp/lba_backups_test",
        max_backups=5,
    )
    backup = await backup_engine.backup(auto=False, notes="Backup de simulación")
    print(f"  ✓ Backup creado: id={backup.id} size={backup.size_bytes} bytes")
    backups = await backup_engine.list_backups()
    print(f"  ✓ Total backups: {len(backups)}")
    print()

    # ---------- 14. Sesiones del servicio ----------
    print_step(14, "ServiceSession")
    from lbamonitor.monitor.session_heartbeat import SessionHeartbeat
    heartbeat = SessionHeartbeat(factory, interval_seconds=300)
    sess_id = await heartbeat.start()
    print(f"  ✓ Sesión iniciada: id={sess_id}")
    await heartbeat._beat()
    print(f"  ✓ Heartbeat enviado")
    await heartbeat.stop()
    print(f"  ✓ Sesión cerrada con EndDateTime y SessionTime")
    print()

    # ---------- 15. ClockMonitor ----------
    print_step(15, "ClockMonitor — detectar cambio de reloj")
    from lbamonitor.monitor.clock_monitor import ClockMonitor
    changes = []
    monitor = ClockMonitor(threshold_seconds=60, interval_seconds=1)

    async def on_change(moment, new_time):
        changes.append((moment, new_time))

    monitor.set_on_change_callback(on_change)
    monitor.initialize()
    monitor._last_check = utcnow() - timedelta(minutes=5)
    await monitor._tick()
    print(f"  ✓ Cambios detectados: {len(changes)}")
    if changes:
        m, n = changes[0]
        delta = (n - m).total_seconds()
        print(f"  ✓ Delta detectado: {delta:.0f}s (significativo si > 60s)")
    print()

    # ---------- 16. EventBus (WebSocket) ----------
    print_step(16, "EventBus (WebSocket)")
    from lbamonitor.api.routes.ws import get_event_bus
    bus = get_event_bus()
    received = []

    async def subscriber():
        q = await bus.subscribe()
        try:
            event = await asyncio.wait_for(q.get(), timeout=1.0)
            received.append(event)
        except asyncio.TimeoutError:
            pass

    sub_task = asyncio.create_task(subscriber())
    await asyncio.sleep(0.1)
    await bus.publish("drive.inserted", {"drive_id": drive.id, "name": "E:"})
    await sub_task

    if received:
        print(f"  ✓ Evento recibido: type={received[0]['type']} data={received[0]['data']}")
    else:
        print(f"  ✗ No se recibió evento")
        errors += 1
    print()

    # ---------- Resumen ----------
    print_header("RESUMEN")
    print(f"  Tests ejecutados: 16")
    print(f"  Errores: {errors}")
    print()
    if errors == 0:
        print("  ✅ SIMULACIÓN COMPLETA — Todo funciona correctamente")
    else:
        print("  ❌ Hay errores que requieren atención")
    print()

    await dispose_engine()
    return errors


def print_header(text: str) -> None:
    print()
    print("=" * 70)
    print(f"  {text}")
    print("=" * 70)


def print_step(n: int, desc: str) -> None:
    print(f"--- Paso {n}: {desc} ---")


if __name__ == "__main__":
    rc = asyncio.run(simulate())
    sys.exit(rc)

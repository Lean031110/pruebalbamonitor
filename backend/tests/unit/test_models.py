"""Tests de modelos SQLAlchemy."""
from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_create_user(db_session: AsyncSession) -> None:
    """Crear y leer un User."""
    from lbamonitor.core.models import User
    u = User(username="admin", role="admin", full_name="Admin User", active=True)
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    assert u.id is not None
    assert u.username == "admin"
    assert u.role == "admin"
    assert u.created is not None


@pytest.mark.asyncio
async def test_create_usb_device_and_session(db_session: AsyncSession) -> None:
    """Crear USBDevice + USBSession + verificar relación."""
    from lbamonitor.core.models import USBDevice, USBSession
    dev = USBDevice(serial_number="ABC123XYZ", name="Kingston DT", brand="Kingston")
    db_session.add(dev)
    await db_session.commit()
    await db_session.refresh(dev)
    assert dev.id is not None

    sess = USBSession(device_id=dev.id, drive_letter="E:\\", label="KINGSTON")
    db_session.add(sess)
    await db_session.commit()
    await db_session.refresh(sess)

    # Recargar dev para ver relación
    await db_session.refresh(dev, attribute_names=["sessions"])
    assert len(dev.sessions) == 1
    assert dev.sessions[0].drive_letter == "E:\\"


@pytest.mark.asyncio
async def test_inserted_drive_with_copies(db_session: AsyncSession) -> None:
    """Crear InsertedDrive + Copy (paridad Uatcher)."""
    from lbamonitor.core.models import Copy, InsertedDrive
    drive = InsertedDrive(
        name="E:\\",
        volume_label="MiUSB",
        space_bytes=32 * 1024 ** 3,
        available_space_bytes=10 * 1024 ** 3,
        serial_number="SERIAL-001",
    )
    db_session.add(drive)
    await db_session.commit()
    await db_session.refresh(drive)

    c1 = Copy(
        inserted_drive_id=drive.id,
        full_path="E:\\pelicula.mp4",
        file_name="pelicula.mp4",
        extension=".mp4",
        size_bytes=1_500_000_000,
    )
    c2 = Copy(
        inserted_drive_id=drive.id,
        full_path="E:\\documento.pdf",
        file_name="documento.pdf",
        extension=".pdf",
        size_bytes=50_000,
    )
    db_session.add_all([c1, c2])
    await db_session.commit()

    # Verificar relación
    await db_session.refresh(drive, attribute_names=["copies"])
    assert len(drive.copies) == 2


@pytest.mark.asyncio
async def test_payment_alteration_relation(db_session: AsyncSession) -> None:
    """Crear PaymentAlteration y verificar FKs."""
    from lbamonitor.core.models import InsertedDrive, PaymentAlteration, User
    user = User(username="operador1", role="operator")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    drive = InsertedDrive(name="F:\\", serial_number="SER-002", user_id=user.id)
    db_session.add(drive)
    await db_session.commit()
    await db_session.refresh(drive)

    # Cambio de pago 0 → 50
    pa1 = PaymentAlteration(
        inserted_drive_id=drive.id, user_id=user.id,
        previous_payment=0, new_payment=50,
    )
    # Cambio 50 → 75
    pa2 = PaymentAlteration(
        inserted_drive_id=drive.id, user_id=user.id,
        previous_payment=50, new_payment=75,
    )
    db_session.add_all([pa1, pa2])
    await db_session.commit()

    await db_session.refresh(drive, attribute_names=["payment_alterations"])
    assert len(drive.payment_alterations) == 2


@pytest.mark.asyncio
async def test_key_value(db_session: AsyncSession) -> None:
    """KeyValue setting genérico (paridad Uatcher)."""
    from lbamonitor.core.models import KeyValue
    kv = KeyValue(key="license", value="abc.def")
    db_session.add(kv)
    await db_session.commit()

    r = await db_session.execute(select(KeyValue).where(KeyValue.key == "license"))
    found = r.scalar_one()
    assert found.value == "abc.def"


@pytest.mark.asyncio
async def test_catalog_entry(db_session: AsyncSession) -> None:
    """CatalogEntry (LBA v3)."""
    from lbamonitor.core.models import CatalogEntry
    cat = CatalogEntry(
        title="Inception",
        category="movie",
        year=2010,
        genre="Sci-Fi",
        director="Christopher Nolan",
        size_gb=4.5,
        rating=8.8,
    )
    db_session.add(cat)
    await db_session.commit()
    await db_session.refresh(cat)
    assert cat.id is not None
    assert cat.title == "Inception"
    assert cat.active is True
    assert cat.times_copied == 0


@pytest.mark.asyncio
async def test_membership_levels(db_session: AsyncSession) -> None:
    """MembershipLevel (LBA v3)."""
    from lbamonitor.core.models import MembershipLevel
    for tier, discount in [("bronce", 0), ("plata", 3), ("oro", 7), ("platino", 12), ("diamante", 20)]:
        db_session.add(MembershipLevel(tier=tier, discount_percent=discount))
    await db_session.commit()

    r = await db_session.execute(select(MembershipLevel).order_by(MembershipLevel.id))
    levels = r.scalars().all()
    assert len(levels) == 5
    assert levels[4].tier == "diamante"
    assert levels[4].discount_percent == 20

"""
Modelos SQLAlchemy 2.0 de LBAMonitor.

Integra el modelo de datos de Uatcher (paridad funcional) con las extensiones
de LBA USB Manager v3.0 (usuarios con roles, membresías, recompensas, catálogo,
plantillas, plugins, etc.).

Tablas:
  - users                       (operadores con roles)
  - usb_devices                 (registro de dispositivos únicos por serial)
  - inserted_drives             (paridad Uatcher: cada inserción)
  - removed_drives              (paridad Uatcher: cada extracción)
  - usb_sessions                (LBA v3: sesión detallada con stats)
  - copies                      (paridad Uatcher: archivos copiados)
  - deletions                   (paridad Uatcher: archivos borrados)
  - file_operations             (LBA v3: evento unificado created/modified/deleted/renamed)
  - payment_alterations         (paridad Uatcher: historial de cambios de pago)
  - billings                    (LBA v3: cobro con PricingEngine completo)
  - clients                     (LBA v3: cliente asociado a un USB)
  - vip_entries                 (LBA v3: tratamiento VIP por USB)
  - membership_levels           (LBA v3: definición de niveles Bronce→Diamante)
  - rewards                     (LBA v3: recompensas otorgadas)
  - catalog_entries             (LBA v3: catálogo multimedia)
  - pc_datetime_changes         (paridad Uatcher: cambios de reloj)
  - service_sessions            (paridad Uatcher: sesiones del servicio)
  - key_values                  (paridad Uatcher: settings genéricas)
  - configuration               (LBA v3: settings flexibles section+key)
  - activity_logs               (LBA v3: auditoría)
  - error_logs                  (LBA v3: errores)
  - backup_records              (LBA v3: historial de backups)
  - notifications               (LBA v3: notificaciones UI)
  - report_records              (LBA v3: historial de reportes)
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    Index,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from lbamonitor.utils.helpers import utcnow


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    """Base declarativa de todos los modelos."""

    def repr(self) -> str:
        cols = {c.name: getattr(self, c.name, None) for c in self.__table__.columns}
        # Solo mostrar PK y campos clave para evitar logs enormes
        pk = self.__table__.primary_key.columns.values()[0].name
        return f"<{self.__class__.__name__} {pk}={cols.get(pk)!r}>"


# ---------------------------------------------------------------------------
# 1. Users — operadores con roles (LBA v3 + paridad Uatcher.User)
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    password_hash: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)  # null = sin login
    role: Mapped[str] = mapped_column(String(16), default="operator", nullable=False)  # admin|manager|operator
    full_name: Mapped[Optional[str]] = mapped_column(String(128))
    email: Mapped[Optional[str]] = mapped_column(String(128))

    # Paridad con Uatcher.User
    name: Mapped[Optional[str]] = mapped_column(String(100))  # alias de full_name para compat
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    inactive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Relaciones
    inserted_drives: Mapped[list["InsertedDrive"]] = relationship(back_populates="user")
    payment_alterations: Mapped[list["PaymentAlteration"]] = relationship(back_populates="user")

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r} role={self.role!r}>"


# ---------------------------------------------------------------------------
# 2. USB Devices — registro único por serial (LBA v3)
# ---------------------------------------------------------------------------

class USBDevice(Base):
    """Dispositivo USB único, identificado por serial number."""

    __tablename__ = "usb_devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    serial_number: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    alias: Mapped[Optional[str]] = mapped_column(String(128), index=True)
    name: Mapped[Optional[str]] = mapped_column(String(256))
    brand: Mapped[Optional[str]] = mapped_column(String(128))
    manufacturer: Mapped[Optional[str]] = mapped_column(String(128))
    model: Mapped[Optional[str]] = mapped_column(String(128))
    vid: Mapped[Optional[str]] = mapped_column(String(16))  # Vendor ID
    pid: Mapped[Optional[str]] = mapped_column(String(16))  # Product ID
    total_capacity: Mapped[Optional[int]] = mapped_column(BigInteger)  # bytes
    connection_type: Mapped[str] = mapped_column(String(16), default="unknown")
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    visit_count: Mapped[int] = mapped_column(Integer, default=0)
    is_known: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relaciones
    sessions: Mapped[list["USBSession"]] = relationship(
        back_populates="device", cascade="all, delete-orphan"
    )
    client: Mapped[Optional["Client"]] = relationship(
        back_populates="device", uselist=False, cascade="all, delete-orphan"
    )
    vip_entry: Mapped[Optional["VIPEntry"]] = relationship(
        back_populates="device", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<USBDevice id={self.id} serial={self.serial_number!r}>"


# ---------------------------------------------------------------------------
# 3. InsertedDrive — paridad con Uatcher (cada inserción de un dispositivo)
# ---------------------------------------------------------------------------

class InsertedDrive(Base):
    """Cada vez que un dispositivo es insertado. Equivalente a Uatcher.InsertedDrive."""

    __tablename__ = "inserted_drives"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    insertion_date_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    # Espacio
    space_bytes: Mapped[Optional[int]] = mapped_column(BigInteger)
    available_space_bytes: Mapped[Optional[int]] = mapped_column(BigInteger)
    available_space_bytes_at_the_end: Mapped[Optional[int]] = mapped_column(BigInteger)

    # Identificación
    name: Mapped[Optional[str]] = mapped_column(String(50))  # E:\
    root_directory: Mapped[Optional[str]] = mapped_column(String(255))
    volume_label: Mapped[Optional[str]] = mapped_column(String(255))
    serial_number: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    model: Mapped[Optional[str]] = mapped_column(String(255))

    # Flags
    is_mobile: Mapped[bool] = mapped_column(Boolean, default=False)
    is_mounted_folder: Mapped[bool] = mapped_column(Boolean, default=False)

    # Pago
    payment: Mapped[Optional[int]] = mapped_column(Integer)  # moneda local int

    # Comentarios
    comment: Mapped[Optional[str]] = mapped_column(Text)
    comment_fixed: Mapped[Optional[str]] = mapped_column(Text)

    # Histórico del dispositivo (calculado al insertar)
    previous_insertions_counter: Mapped[int] = mapped_column(Integer, default=0)
    previous_payments_sum: Mapped[int] = mapped_column(Integer, default=0)

    # UI
    row_color: Mapped[int] = mapped_column(Integer, default=0)

    # FKs
    removed_drive_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("removed_drives.id"), nullable=True
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )

    # Relación con USBDevice (nueva, LBA v3)
    usb_device_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("usb_devices.id"), nullable=True, index=True
    )

    # Relaciones
    removed_drive: Mapped[Optional["RemovedDrive"]] = relationship(back_populates="inserted_drive")
    user: Mapped[Optional["User"]] = relationship(back_populates="inserted_drives")
    copies: Mapped[list["Copy"]] = relationship(
        back_populates="inserted_drive", cascade="all, delete-orphan"
    )
    deletions: Mapped[list["Deletion"]] = relationship(
        back_populates="inserted_drive", cascade="all, delete-orphan"
    )
    payment_alterations: Mapped[list["PaymentAlteration"]] = relationship(
        back_populates="inserted_drive", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_inserted_drives_serial_insertion", "serial_number", "insertion_date_time"),
    )

    def __repr__(self) -> str:
        return f"<InsertedDrive id={self.id} name={self.name!r} at={self.insertion_date_time}>"


# ---------------------------------------------------------------------------
# 4. RemovedDrive — paridad con Uatcher
# ---------------------------------------------------------------------------

class RemovedDrive(Base):
    __tablename__ = "removed_drives"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    removal_date_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(50))
    root_directory: Mapped[Optional[str]] = mapped_column(String(255))

    inserted_drive: Mapped[Optional["InsertedDrive"]] = relationship(back_populates="removed_drive")

    def __repr__(self) -> str:
        return f"<RemovedDrive id={self.id} name={self.name!r} at={self.removal_date_time}>"


# ---------------------------------------------------------------------------
# 5. USBSession — LBA v3: sesión detallada con stats
# ---------------------------------------------------------------------------

class USBSession(Base):
    """Sesión de uso de un USB, con estadísticas detalladas (LBA v3)."""

    __tablename__ = "usb_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("usb_devices.id", ondelete="CASCADE"), index=True
    )

    drive_letter: Mapped[Optional[str]] = mapped_column(String(4))
    label: Mapped[Optional[str]] = mapped_column(String(256))
    filesystem: Mapped[Optional[str]] = mapped_column(String(32))

    total_capacity: Mapped[Optional[int]] = mapped_column(BigInteger)
    free_capacity_at_connect: Mapped[Optional[int]] = mapped_column(BigInteger)
    free_capacity_at_disconnect: Mapped[Optional[int]] = mapped_column(BigInteger)

    port: Mapped[Optional[str]] = mapped_column(String(64))
    speed: Mapped[Optional[str]] = mapped_column(String(32))

    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    disconnected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer)

    files_copied: Mapped[int] = mapped_column(Integer, default=0)
    files_deleted: Mapped[int] = mapped_column(Integer, default=0)
    files_modified: Mapped[int] = mapped_column(Integer, default=0)
    bytes_copied: Mapped[int] = mapped_column(BigInteger, default=0)
    operation_count: Mapped[int] = mapped_column(Integer, default=0)

    avg_speed_mbps: Mapped[Optional[float]] = mapped_column(Float)
    max_speed_mbps: Mapped[Optional[float]] = mapped_column(Float)

    # Conteos por categoría
    count_video: Mapped[int] = mapped_column(Integer, default=0)
    count_movie: Mapped[int] = mapped_column(Integer, default=0)
    count_series: Mapped[int] = mapped_column(Integer, default=0)
    count_music: Mapped[int] = mapped_column(Integer, default=0)
    count_document: Mapped[int] = mapped_column(Integer, default=0)
    count_image: Mapped[int] = mapped_column(Integer, default=0)
    count_game: Mapped[int] = mapped_column(Integer, default=0)
    count_app: Mapped[int] = mapped_column(Integer, default=0)
    count_other: Mapped[int] = mapped_column(Integer, default=0)

    notes: Mapped[Optional[str]] = mapped_column(Text)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relaciones
    device: Mapped["USBDevice"] = relationship(back_populates="sessions")
    billing: Mapped[Optional["Billing"]] = relationship(
        back_populates="session", uselist=False, cascade="all, delete-orphan"
    )
    operations: Mapped[list["FileOperation"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<USBSession id={self.id} device_id={self.device_id} at={self.connected_at}>"


# ---------------------------------------------------------------------------
# 6. Copy — paridad con Uatcher (archivos copiados)
# ---------------------------------------------------------------------------

class Copy(Base):
    __tablename__ = "copies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    copy_date_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    full_path: Mapped[str] = mapped_column(String(1024))
    extension: Mapped[Optional[str]] = mapped_column(String(20), index=True)
    file_name: Mapped[Optional[str]] = mapped_column(String(255))
    size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger)

    inserted_drive_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("inserted_drives.id"), index=True
    )

    # FK opcional a USBSession (LBA v3)
    session_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("usb_sessions.id", ondelete="CASCADE"), index=True
    )
    category: Mapped[Optional[str]] = mapped_column(String(16))  # LBA v3: video|music|...

    inserted_drive: Mapped[Optional["InsertedDrive"]] = relationship(back_populates="copies")

    __table_args__ = (
        Index("ix_copies_date_ext", "copy_date_time", "extension"),
    )

    def __repr__(self) -> str:
        return f"<Copy id={self.id} file={self.file_name!r} size={self.size_bytes}>"


# ---------------------------------------------------------------------------
# 7. Deletion — paridad con Uatcher
# ---------------------------------------------------------------------------

class Deletion(Base):
    __tablename__ = "deletions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    deletion_date_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    full_path: Mapped[str] = mapped_column(String(1024))
    extension: Mapped[Optional[str]] = mapped_column(String(20), index=True)
    file_name: Mapped[Optional[str]] = mapped_column(String(255))

    inserted_drive_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("inserted_drives.id"), index=True
    )

    inserted_drive: Mapped[Optional["InsertedDrive"]] = relationship(back_populates="deletions")

    def __repr__(self) -> str:
        return f"<Deletion id={self.id} file={self.file_name!r}>"


# ---------------------------------------------------------------------------
# 8. FileOperation — LBA v3: evento unificado
# ---------------------------------------------------------------------------

class FileOperation(Base):
    """Evento unificado de filesystem: created/modified/deleted/renamed."""

    __tablename__ = "file_operations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("usb_sessions.id", ondelete="CASCADE"), index=True
    )
    operation: Mapped[str] = mapped_column(String(16))  # created|modified|deleted|renamed
    file_path: Mapped[str] = mapped_column(Text)
    file_name: Mapped[Optional[str]] = mapped_column(String(512))
    file_ext: Mapped[Optional[str]] = mapped_column(String(16))
    file_size: Mapped[Optional[int]] = mapped_column(BigInteger)
    category: Mapped[Optional[str]] = mapped_column(String(16))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    session: Mapped["USBSession"] = relationship(back_populates="operations")

    def __repr__(self) -> str:
        return f"<FileOperation id={self.id} op={self.operation!r} file={self.file_name!r}>"


# ---------------------------------------------------------------------------
# 9. PaymentAlteration — paridad con Uatcher (historial de cambios de pago)
# ---------------------------------------------------------------------------

class PaymentAlteration(Base):
    __tablename__ = "payment_alterations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    previous_payment: Mapped[Optional[int]] = mapped_column(Integer)
    new_payment: Mapped[Optional[int]] = mapped_column(Integer)
    alteration_date_time: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, index=True
    )

    inserted_drive_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("inserted_drives.id"), index=True
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )

    inserted_drive: Mapped["InsertedDrive"] = relationship(back_populates="payment_alterations")
    user: Mapped[Optional["User"]] = relationship(back_populates="payment_alterations")

    def __repr__(self) -> str:
        return (
            f"<PaymentAlteration id={self.id} "
            f"{self.previous_payment}→{self.new_payment} at={self.alteration_date_time}>"
        )


# ---------------------------------------------------------------------------
# 10. Billing — LBA v3: cobro con PricingEngine completo
# ---------------------------------------------------------------------------

class Billing(Base):
    __tablename__ = "billings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("usb_sessions.id", ondelete="CASCADE"), unique=True
    )
    device_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("usb_devices.id"), index=True
    )

    pricing_mode: Mapped[Optional[str]] = mapped_column(String(16))
    suggested_price: Mapped[Optional[float]] = mapped_column(Float)
    discount_percent: Mapped[float] = mapped_column(Float, default=0.0)
    discount_amount: Mapped[float] = mapped_column(Float, default=0.0)
    tax_percent: Mapped[float] = mapped_column(Float, default=0.0)
    tax_amount: Mapped[float] = mapped_column(Float, default=0.0)
    total: Mapped[float] = mapped_column(Float, default=0.0)
    charged: Mapped[Optional[float]] = mapped_column(Float)

    observations: Mapped[Optional[str]] = mapped_column(Text)
    not_charged: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(64))

    session: Mapped["USBSession"] = relationship(back_populates="billing")

    def __repr__(self) -> str:
        return f"<Billing id={self.id} charged={self.charged}>"


# ---------------------------------------------------------------------------
# 11. Client — LBA v3: cliente asociado a un USB
# ---------------------------------------------------------------------------

class Client(Base):
    """Cliente asociado a un USB (relación 1:1)."""

    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("usb_devices.id", ondelete="CASCADE"), unique=True
    )
    name: Mapped[Optional[str]] = mapped_column(String(128))
    phone: Mapped[Optional[str]] = mapped_column(String(32))
    photo_path: Mapped[Optional[str]] = mapped_column(String(512))
    observations: Mapped[Optional[str]] = mapped_column(Text)

    visit_count: Mapped[int] = mapped_column(Integer, default=0)
    total_spent: Mapped[float] = mapped_column(Float, default=0.0)
    total_gb_copied: Mapped[float] = mapped_column(Float, default=0.0)

    first_visit: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_visit: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    points: Mapped[int] = mapped_column(Integer, default=0)
    tier: Mapped[str] = mapped_column(String(16), default="bronce")

    device: Mapped["USBDevice"] = relationship(back_populates="client")

    def __repr__(self) -> str:
        return f"<Client id={self.id} name={self.name!r} tier={self.tier!r}>"


# ---------------------------------------------------------------------------
# 12. VIPEntry — LBA v3
# ---------------------------------------------------------------------------

class VIPEntry(Base):
    __tablename__ = "vip_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("usb_devices.id", ondelete="CASCADE"), unique=True
    )
    vip_type: Mapped[str] = mapped_column(String(16), default="none")
    discount_percent: Mapped[Optional[float]] = mapped_column(Float)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    device: Mapped["USBDevice"] = relationship(back_populates="vip_entry")

    def __repr__(self) -> str:
        return f"<VIPEntry id={self.id} device_id={self.device_id} type={self.vip_type!r}>"


# ---------------------------------------------------------------------------
# 13. MembershipLevel — LBA v3
# ---------------------------------------------------------------------------

class MembershipLevel(Base):
    __tablename__ = "membership_levels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tier: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    min_visits: Mapped[int] = mapped_column(Integer, default=0)
    min_gb: Mapped[float] = mapped_column(Float, default=0.0)
    min_spent: Mapped[float] = mapped_column(Float, default=0.0)
    discount_percent: Mapped[float] = mapped_column(Float, default=0.0)
    color: Mapped[Optional[str]] = mapped_column(String(16))

    def __repr__(self) -> str:
        return f"<MembershipLevel tier={self.tier!r} discount={self.discount_percent}%>"


# ---------------------------------------------------------------------------
# 14. Reward — LBA v3
# ---------------------------------------------------------------------------

class Reward(Base):
    __tablename__ = "rewards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("usb_devices.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reward_type: Mapped[str] = mapped_column(String(32))  # free|discount|gift|bonus|frequent|month
    description: Mapped[Optional[str]] = mapped_column(Text)
    value: Mapped[Optional[float]] = mapped_column(Float)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    applied: Mapped[bool] = mapped_column(Boolean, default=False)

    def __repr__(self) -> str:
        return f"<Reward id={self.id} type={self.reward_type!r} value={self.value}>"


# ---------------------------------------------------------------------------
# 15. CatalogEntry — LBA v3: catálogo multimedia
# ---------------------------------------------------------------------------

class CatalogEntry(Base):
    __tablename__ = "catalog_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(32), index=True)
    year: Mapped[Optional[int]] = mapped_column(Integer)
    genre: Mapped[Optional[str]] = mapped_column(String(128))
    director: Mapped[Optional[str]] = mapped_column(String(128))
    artist: Mapped[Optional[str]] = mapped_column(String(128))
    description: Mapped[Optional[str]] = mapped_column(Text)

    size_gb: Mapped[Optional[float]] = mapped_column(Float)
    rating: Mapped[Optional[float]] = mapped_column(Float)  # 0-10
    duration_minutes: Mapped[Optional[int]] = mapped_column(Integer)

    cover_path: Mapped[Optional[str]] = mapped_column(String(512))
    file_path: Mapped[Optional[str]] = mapped_column(String(512))
    tags: Mapped[Optional[str]] = mapped_column(String(256))  # CSV

    times_copied: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )

    def __repr__(self) -> str:
        return f"<CatalogEntry id={self.id} title={self.title!r} category={self.category!r}>"


# ---------------------------------------------------------------------------
# 16. PCDatetimeChange — paridad con Uatcher
# ---------------------------------------------------------------------------

class PCDatetimeChange(Base):
    __tablename__ = "pc_datetime_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    moment: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    to: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<PCDatetimeChange id={self.id} moment={self.moment} to={self.to}>"


# ---------------------------------------------------------------------------
# 17. ServiceSession — paridad con Uatcher
# ---------------------------------------------------------------------------

class ServiceSession(Base):
    __tablename__ = "service_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    start_date_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    end_date_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    alive_date_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    session_time: Mapped[Optional[int]] = mapped_column(Integer)  # seconds

    def __repr__(self) -> str:
        return f"<ServiceSession id={self.id} start={self.start_date_time}>"


# ---------------------------------------------------------------------------
# 18. KeyValue — paridad con Uatcher
# ---------------------------------------------------------------------------

class KeyValue(Base):
    __tablename__ = "key_values"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    value: Mapped[Optional[str]] = mapped_column(Text)

    def __repr__(self) -> str:
        return f"<KeyValue key={self.key!r} value={self.value!r}>"


# ---------------------------------------------------------------------------
# 19. Configuration — LBA v3: settings flexibles section+key
# ---------------------------------------------------------------------------

class Configuration(Base):
    """Settings flexibles con tipado, complementa KeyValue."""

    __tablename__ = "configuration"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    section: Mapped[str] = mapped_column(String(64), index=True)
    key: Mapped[str] = mapped_column(String(128), index=True)
    value: Mapped[Optional[str]] = mapped_column(Text)
    value_type: Mapped[str] = mapped_column(String(16), default="str")  # str|int|float|bool|json
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )

    __table_args__ = (
        UniqueConstraint("section", "key", name="uq_configuration_section_key"),
    )

    def __repr__(self) -> str:
        return f"<Configuration {self.section}.{self.key}={self.value!r}>"


# ---------------------------------------------------------------------------
# 20. ActivityLog — LBA v3: auditoría
# ---------------------------------------------------------------------------

class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user: Mapped[Optional[str]] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))  # login|create|update|delete|...
    entity: Mapped[Optional[str]] = mapped_column(String(64))
    entity_id: Mapped[Optional[int]] = mapped_column(Integer)
    details: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    def __repr__(self) -> str:
        return f"<ActivityLog id={self.id} action={self.action!r} user={self.user!r}>"


# ---------------------------------------------------------------------------
# 21. ErrorLog — LBA v3
# ---------------------------------------------------------------------------

class ErrorLog(Base):
    __tablename__ = "error_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    level: Mapped[str] = mapped_column(String(16), default="ERROR")
    module: Mapped[Optional[str]] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(Text)
    traceback: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    def __repr__(self) -> str:
        return f"<ErrorLog id={self.id} level={self.level!r} module={self.module!r}>"


# ---------------------------------------------------------------------------
# 22. BackupRecord — LBA v3
# ---------------------------------------------------------------------------

class BackupRecord(Base):
    __tablename__ = "backup_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_path: Mapped[str] = mapped_column(String(512))
    size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger)
    auto: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    def __repr__(self) -> str:
        return f"<BackupRecord id={self.id} file={self.file_path!r}>"


# ---------------------------------------------------------------------------
# 23. Notification — LBA v3
# ---------------------------------------------------------------------------

class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(128))
    message: Mapped[Optional[str]] = mapped_column(Text)
    level: Mapped[str] = mapped_column(String(16), default="info")  # info|warn|error|success
    category: Mapped[str] = mapped_column(String(32), default="usb")
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    def __repr__(self) -> str:
        return f"<Notification id={self.id} title={self.title!r} level={self.level!r}>"


# ---------------------------------------------------------------------------
# 24. ReportRecord — LBA v3
# ---------------------------------------------------------------------------

class ReportRecord(Base):
    __tablename__ = "report_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))
    report_type: Mapped[str] = mapped_column(String(32))  # daily|monthly|annual|custom
    format: Mapped[str] = mapped_column(String(8))  # pdf|excel|csv|html
    file_path: Mapped[str] = mapped_column(String(512))
    period_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_by: Mapped[Optional[str]] = mapped_column(String(64))

    def __repr__(self) -> str:
        return f"<ReportRecord id={self.id} name={self.name!r} format={self.format!r}>"


# Re-export para conveniencia (from lbamonitor.core.models import User, USBDevice, ...)
__all__ = [
    "ActivityLog",
    "BackupRecord",
    "Base",
    "Billing",
    "CatalogEntry",
    "Client",
    "Configuration",
    "Copy",
    "Deletion",
    "ErrorLog",
    "FileOperation",
    "InsertedDrive",
    "KeyValue",
    "MembershipLevel",
    "Notification",
    "PCDatetimeChange",
    "PaymentAlteration",
    "RemovedDrive",
    "ReportRecord",
    "Reward",
    "ServiceSession",
    "USBDevice",
    "USBSession",
    "User",
    "VIPEntry",
]

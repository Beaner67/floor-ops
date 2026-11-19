"""Domain model.

Privacy by design: nothing here identifies a customer. Vision tracks are
ephemeral and never stored; we persist only operational facts (a table became
occupied, a hand was raised at table 3, a surface looked clear).
"""
from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Stores naive UTC, always returns tz-aware UTC (SQLite drops tzinfo)."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime passed to UTCDateTime")
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=timezone.utc) if value is not None else None


class TableStatus(StrEnum):
    VACANT = "vacant"
    OCCUPIED = "occupied"
    NEEDS_CLEANING = "needs_cleaning"
    OUT_OF_SERVICE = "out_of_service"


class TaskType(StrEnum):
    CLEAN_TABLE = "clean_table"
    ASSIST_CUSTOMER = "assist_customer"   # raised hand
    ATTEND_TABLE = "attend_table"         # seated too long without any staff visit
    DELIVER_ORDER = "deliver_order"
    CHECK_ORDER = "check_order"           # kitchen delay
    GENERAL = "general"                   # created manually at the counter


class TaskStatus(StrEnum):
    PENDING = "pending"                       # created, nobody assigned
    ASSIGNED = "assigned"
    AWAITING_VERIFICATION = "awaiting_verification"  # staff said done, AI checking
    VERIFIED = "verified"
    VERIFICATION_FAILED = "verification_failed"
    VERIFICATION_UNCERTAIN = "verification_uncertain"
    DONE = "done"                             # no visual check applicable
    CANCELLED = "cancelled"


OPEN_TASK_STATUSES = (
    TaskStatus.PENDING,
    TaskStatus.ASSIGNED,
    TaskStatus.AWAITING_VERIFICATION,
    TaskStatus.VERIFICATION_FAILED,
    TaskStatus.VERIFICATION_UNCERTAIN,
)


class Priority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


PRIORITY_RANK = {Priority.LOW: 0, Priority.MEDIUM: 1, Priority.HIGH: 2}


class OrderStatus(StrEnum):
    PLACED = "placed"
    PREPARING = "preparing"
    READY = "ready"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class Camera(Base):
    __tablename__ = "cameras"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    online: Mapped[bool] = mapped_column(Boolean, default=False)


class Integration(Base):
    """Health of push-based integrations (e.g. the POS feed): when did it last talk to us."""

    __tablename__ = "integrations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # "pos"
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    online: Mapped[bool] = mapped_column(Boolean, default=False)


class DiningTable(Base):
    __tablename__ = "tables"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String(20), unique=True)
    capacity: Mapped[int] = mapped_column(Integer, default=4)
    camera_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Floor-plan position (0-100 % of the plan) for the counter dashboard map.
    pos_x: Mapped[float] = mapped_column(default=0)
    pos_y: Mapped[float] = mapped_column(default=0)

    status: Mapped[str] = mapped_column(String(20), default=TableStatus.VACANT)
    status_since: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    current_seating_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Latest camera reading of objects left on the table surface (cups, plates…).
    surface_items: Mapped[int | None] = mapped_column(Integer, nullable=True)
    surface_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class Seating(Base):
    """One party's stay at a table. Anonymous: only times and head count."""

    __tablename__ = "seatings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("tables.id"), index=True)
    party_size: Mapped[int] = mapped_column(Integer, default=0)
    seated_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    first_attended_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    left_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class Staff(Base):
    __tablename__ = "staff"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    role: Mapped[str] = mapped_column(String(40), default="server")
    on_shift: Mapped[bool] = mapped_column(Boolean, default=True)


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(30), index=True)
    priority: Mapped[str] = mapped_column(String(10), default=Priority.MEDIUM)
    status: Mapped[str] = mapped_column(String(30), default=TaskStatus.PENDING, index=True)
    title: Mapped[str] = mapped_column(String(200))
    detail: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(20), default="ai")  # ai | pos | manual

    table_id: Mapped[int | None] = mapped_column(ForeignKey("tables.id"), nullable=True, index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True)
    staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    due_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    assigned_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    verification_note: Mapped[str] = mapped_column(Text, default="")
    verified_by: Mapped[str | None] = mapped_column(String(20), nullable=True)  # ai | manual


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Dedup key: at most one open alert per key (e.g. "assist_unattended:task:12").
    key: Mapped[str] = mapped_column(String(120), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    priority: Mapped[str] = mapped_column(String(10))
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text, default="")
    table_id: Mapped[int | None] = mapped_column(ForeignKey("tables.id"), nullable=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pos_ref: Mapped[str] = mapped_column(String(64), unique=True)
    table_id: Mapped[int | None] = mapped_column(ForeignKey("tables.id"), nullable=True)
    items: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default=OrderStatus.PLACED)
    sla_minutes: Mapped[int] = mapped_column(Integer, default=15)
    placed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    ready_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class Observation(Base):
    """Append-only log of every event received from cameras (audit + evidence)."""

    __tablename__ = "observations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    type: Mapped[str] = mapped_column(String(40), index=True)
    camera_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    table_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)


class OccupancySample(Base):
    __tablename__ = "occupancy_samples"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    people_inside: Mapped[int] = mapped_column(Integer)
    occupied_tables: Mapped[int] = mapped_column(Integer)

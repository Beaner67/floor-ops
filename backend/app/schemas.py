from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- events from vision workers ----------

EventType = Literal[
    "table.occupied",       # data: {party_size}
    "table.vacated",
    "table.attended",       # a non-seated person (staff) stayed at the table >= N seconds
    "table.surface",        # data: {items}  objects detected on the table surface
    "service.hand_raised",
    "people.count",         # data: {inside}
    "entrance.enter",
    "entrance.exit",
    "camera.heartbeat",
]


class EventIn(BaseModel):
    type: EventType
    camera_id: str | None = None
    table_id: int | None = None
    table: str | None = Field(None, description="Table label, alternative to table_id")
    ts: datetime | None = None
    data: dict[str, Any] = {}


# ---------- read models ----------

class TableOut(ORM):
    id: int
    label: str
    capacity: int
    camera_id: str | None
    pos_x: float
    pos_y: float
    status: str
    status_since: datetime
    surface_items: int | None
    surface_seen_at: datetime | None
    seated_at: datetime | None = None
    party_size: int | None = None
    first_attended_at: datetime | None = None


class StaffOut(ORM):
    id: int
    name: str
    role: str
    on_shift: bool


class TaskOut(ORM):
    id: int
    type: str
    priority: str
    status: str
    title: str
    detail: str
    source: str
    table_id: int | None
    table_label: str | None = None
    order_id: int | None
    staff_id: int | None
    staff_name: str | None = None
    created_at: datetime
    due_at: datetime | None
    assigned_at: datetime | None
    completed_at: datetime | None
    closed_at: datetime | None
    verification_note: str
    verified_by: str | None


class AlertOut(ORM):
    id: int
    key: str
    kind: str
    priority: str
    title: str
    message: str
    table_id: int | None
    task_id: int | None
    created_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None


class OrderOut(ORM):
    id: int
    pos_ref: str
    table_id: int | None
    table_label: str | None = None
    items: str
    status: str
    sla_minutes: int
    placed_at: datetime
    ready_at: datetime | None
    delivered_at: datetime | None


class CameraOut(ORM):
    id: str
    name: str
    last_seen_at: datetime | None
    online: bool


class IntegrationOut(ORM):
    id: str
    last_seen_at: datetime | None
    online: bool


class StateOut(BaseModel):
    tables: list[TableOut]
    tasks: list[TaskOut]
    alerts: list[AlertOut]
    staff: list[StaffOut]
    orders: list[OrderOut]
    cameras: list[CameraOut]
    integrations: list[IntegrationOut]
    server_time: datetime


# ---------- commands ----------

class TaskCreate(BaseModel):
    title: str
    detail: str = ""
    table_id: int | None = None
    priority: Literal["low", "medium", "high"] = "medium"
    staff_id: int | None = None


class AssignIn(BaseModel):
    staff_id: int


class ReviewIn(BaseModel):
    decision: Literal["confirm", "redo"]
    note: str = ""


class StaffIn(BaseModel):
    name: str
    role: str = "server"
    on_shift: bool = True


class StaffPatch(BaseModel):
    name: str | None = None
    role: str | None = None
    on_shift: bool | None = None


class TableIn(BaseModel):
    label: str
    capacity: int = 4
    camera_id: str | None = None
    pos_x: float = 50
    pos_y: float = 50


class TablePatch(BaseModel):
    status: Literal["vacant", "out_of_service"] | None = None
    capacity: int | None = None
    pos_x: float | None = None
    pos_y: float | None = None


class PosOrderIn(BaseModel):
    pos_ref: str
    table_id: int | None = None
    table: str | None = None
    items: str = ""
    status: Literal["placed", "preparing", "ready", "delivered", "cancelled"] = "placed"
    sla_minutes: int | None = None
    ts: datetime | None = None


class PosStatusIn(BaseModel):
    status: Literal["placed", "preparing", "ready", "delivered", "cancelled"]
    ts: datetime | None = None

from sqlalchemy.orm import Session

from .models import Alert, Camera, DiningTable, Integration, Order, Seating, Staff, Task
from .schemas import AlertOut, CameraOut, IntegrationOut, OrderOut, StaffOut, TableOut, TaskOut


def table_out(db: Session, t: DiningTable) -> TableOut:
    out = TableOut.model_validate(t)
    if t.current_seating_id:
        s = db.get(Seating, t.current_seating_id)
        if s:
            out.seated_at, out.party_size, out.first_attended_at = s.seated_at, s.party_size, s.first_attended_at
    return out


def task_out(db: Session, t: Task) -> TaskOut:
    out = TaskOut.model_validate(t)
    if t.table_id:
        table = db.get(DiningTable, t.table_id)
        out.table_label = table.label if table else None
    if t.staff_id:
        staff = db.get(Staff, t.staff_id)
        out.staff_name = staff.name if staff else None
    return out


def order_out(db: Session, o: Order) -> OrderOut:
    out = OrderOut.model_validate(o)
    if o.table_id:
        table = db.get(DiningTable, o.table_id)
        out.table_label = table.label if table else None
    return out


def alert_out(a: Alert) -> AlertOut:
    return AlertOut.model_validate(a)


def staff_out(s: Staff) -> StaffOut:
    return StaffOut.model_validate(s)


def camera_out(c: Camera) -> CameraOut:
    return CameraOut.model_validate(c)


def integration_out(i: Integration) -> IntegrationOut:
    return IntegrationOut.model_validate(i)

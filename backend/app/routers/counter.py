"""Human-facing endpoints used by the counter device, staff phones and manager view."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..bus import emit
from ..db import get_db
from ..deps import now
from ..engine import ops
from ..engine.lock import write_lock
from ..models import (
    OPEN_TASK_STATUSES,
    Alert,
    Camera,
    DiningTable,
    Integration,
    Order,
    OrderStatus,
    Priority,
    Staff,
    Task,
    TaskType,
)
from ..schemas import (
    AlertOut,
    AssignIn,
    ReviewIn,
    StaffIn,
    StaffOut,
    StaffPatch,
    StateOut,
    TableIn,
    TableOut,
    TablePatch,
    TaskCreate,
    TaskOut,
)
from ..serialize import alert_out, camera_out, integration_out, order_out, staff_out, table_out, task_out
from ..config import settings

router = APIRouter(prefix="/api", tags=["counter"])


def _get(db: Session, model, id_):
    obj = db.get(model, id_)
    if obj is None:
        raise HTTPException(404, f"{model.__name__} {id_} not found")
    return obj


def _run(fn):
    try:
        fn()
    except ops.DomainError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/state", response_model=StateOut)
def state(db: Session = Depends(get_db)):
    """Everything the counter dashboard needs on load; WebSocket deltas follow."""
    t = now()
    recent_cut = t.replace(hour=0, minute=0, second=0, microsecond=0)
    tasks = db.scalars(select(Task).where(or_(Task.status.in_(OPEN_TASK_STATUSES), Task.closed_at >= recent_cut))
                       .order_by(Task.created_at.desc()).limit(300))
    alerts = db.scalars(select(Alert).where(or_(Alert.resolved_at.is_(None), Alert.created_at >= recent_cut))
                        .order_by(Alert.created_at.desc()).limit(200))
    orders = db.scalars(select(Order).where(Order.status.in_(
        (OrderStatus.PLACED, OrderStatus.PREPARING, OrderStatus.READY))).order_by(Order.placed_at))
    return StateOut(
        tables=[table_out(db, x) for x in db.scalars(select(DiningTable).order_by(DiningTable.id))],
        tasks=[task_out(db, x) for x in tasks],
        alerts=[alert_out(x) for x in alerts],
        staff=[staff_out(x) for x in db.scalars(select(Staff).order_by(Staff.name))],
        orders=[order_out(db, x) for x in orders],
        cameras=[camera_out(x) for x in db.scalars(select(Camera).order_by(Camera.id))],
        integrations=[integration_out(x) for x in db.scalars(select(Integration))],
        server_time=t,
    )


@router.get("/settings")
def get_settings() -> dict:
    return settings.model_dump(exclude={"database_url", "device_key", "notify_url"})


# ---------------------------------------------------------------- tasks

@router.post("/tasks", response_model=TaskOut)
def create_task(body: TaskCreate, db: Session = Depends(get_db)):
    with write_lock:
        table = _get(db, DiningTable, body.table_id) if body.table_id else None
        if body.staff_id:
            _get(db, Staff, body.staff_id)
        task = ops.create_task(db, type=TaskType.GENERAL, title=body.title, detail=body.detail, table=table,
                               priority=Priority(body.priority), due_s=settings.generic_task_due_s, now=now(),
                               source="manual", staff_id=body.staff_id)
        db.commit()
        return task_out(db, task)


@router.post("/tasks/{task_id}/assign", response_model=TaskOut)
def assign(task_id: int, body: AssignIn, db: Session = Depends(get_db)):
    with write_lock:
        task, staff = _get(db, Task, task_id), _get(db, Staff, body.staff_id)
        _run(lambda: ops.assign_task(db, task, staff, now()))
        db.commit()
        return task_out(db, task)


@router.post("/tasks/{task_id}/complete", response_model=TaskOut)
def complete(task_id: int, db: Session = Depends(get_db)):
    with write_lock:
        task = _get(db, Task, task_id)
        _run(lambda: ops.complete_task(db, task, now()))
        db.commit()
        return task_out(db, task)


@router.post("/tasks/{task_id}/review", response_model=TaskOut)
def review(task_id: int, body: ReviewIn, db: Session = Depends(get_db)):
    with write_lock:
        task = _get(db, Task, task_id)
        _run(lambda: ops.review_task(db, task, body.decision, body.note, now()))
        db.commit()
        return task_out(db, task)


@router.post("/tasks/{task_id}/cancel", response_model=TaskOut)
def cancel(task_id: int, db: Session = Depends(get_db)):
    with write_lock:
        task = _get(db, Task, task_id)
        _run(lambda: ops.cancel_task(db, task, now()))
        db.commit()
        return task_out(db, task)


# ---------------------------------------------------------------- alerts

@router.post("/alerts/{alert_id}/ack", response_model=AlertOut)
def ack_alert(alert_id: int, db: Session = Depends(get_db)):
    with write_lock:
        alert = _get(db, Alert, alert_id)
        if alert.acknowledged_at is None:
            alert.acknowledged_at = now()
            db.flush()
            emit(db, "alert", alert_out(alert).model_dump(mode="json"))
        db.commit()
        return alert_out(alert)


# ---------------------------------------------------------------- tables & staff

@router.post("/tables", response_model=TableOut)
def add_table(body: TableIn, db: Session = Depends(get_db)):
    with write_lock:
        if db.scalar(select(DiningTable.id).where(DiningTable.label == body.label)):
            raise HTTPException(409, "table label already exists")
        table = DiningTable(**body.model_dump(), status_since=now())
        db.add(table)
        db.flush()
        emit(db, "table", table_out(db, table).model_dump(mode="json"))
        db.commit()
        return table_out(db, table)


@router.patch("/tables/{table_id}", response_model=TableOut)
def patch_table(table_id: int, body: TablePatch, db: Session = Depends(get_db)):
    with write_lock:
        table = _get(db, DiningTable, table_id)
        for field in ("capacity", "pos_x", "pos_y"):
            if (v := getattr(body, field)) is not None:
                setattr(table, field, v)
        if body.status:
            ops.set_table_manual(db, table, body.status, now())
        else:
            db.flush()
            emit(db, "table", table_out(db, table).model_dump(mode="json"))
        db.commit()
        return table_out(db, table)


@router.post("/staff", response_model=StaffOut)
def add_staff(body: StaffIn, db: Session = Depends(get_db)):
    with write_lock:
        s = Staff(**body.model_dump())
        db.add(s)
        db.flush()
        emit(db, "staff", staff_out(s).model_dump(mode="json"))
        db.commit()
        return staff_out(s)


@router.patch("/staff/{staff_id}", response_model=StaffOut)
def patch_staff(staff_id: int, body: StaffPatch, db: Session = Depends(get_db)):
    with write_lock:
        s = _get(db, Staff, staff_id)
        for k, v in body.model_dump(exclude_none=True).items():
            setattr(s, k, v)
        db.flush()
        emit(db, "staff", staff_out(s).model_dump(mode="json"))
        db.commit()
        return staff_out(s)

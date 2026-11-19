"""Operations engine: turns camera observations and POS updates into table
state, staff tasks, alerts and AI verification decisions.

Design notes
- Pure domain logic over a SQLAlchemy session; callers own the transaction.
- Every function takes an explicit `now` so behaviour is deterministic in tests.
- Two entry points: `handle_event` (something was observed) and `tick` (time
  passed; check SLAs). Tick is idempotent, so it is safe to call as often as needed.
- Alerts are de-duplicated by key, so a condition raises one alert, not one per tick.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..bus import emit, queue_notification
from ..config import settings
from ..models import (
    OPEN_TASK_STATUSES,
    Alert,
    Camera,
    DiningTable,
    Integration,
    Observation,
    OccupancySample,
    Order,
    OrderStatus,
    Priority,
    Seating,
    Staff,
    TableStatus,
    Task,
    TaskStatus,
    TaskType,
)
from ..schemas import EventIn
from ..serialize import alert_out, camera_out, integration_out, order_out, table_out, task_out

# Task types whose completion the cameras can check.
VERIFIABLE = {TaskType.CLEAN_TABLE, TaskType.ASSIST_CUSTOMER, TaskType.ATTEND_TABLE, TaskType.DELIVER_ORDER}


class DomainError(Exception):
    """Invalid command for the current state (maps to HTTP 409)."""


# --------------------------------------------------------------------------- helpers

def _aware(ts: datetime | None, now: datetime) -> datetime:
    if ts is None:
        return now
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def _hhmm(ts: datetime) -> str:
    return ts.astimezone().strftime("%H:%M")


def _emit_table(db: Session, t: DiningTable) -> None:
    db.flush()
    emit(db, "table", table_out(db, t).model_dump(mode="json"))


def _emit_task(db: Session, t: Task) -> None:
    db.flush()
    emit(db, "task", task_out(db, t).model_dump(mode="json"))


def _emit_order(db: Session, o: Order) -> None:
    db.flush()
    emit(db, "order", order_out(db, o).model_dump(mode="json"))


def set_table_status(db: Session, table: DiningTable, status: TableStatus, at: datetime) -> None:
    if table.status != status:
        table.status = status
        table.status_since = at
    _emit_table(db, table)


def resolve_table(db: Session, table_id: int | None, label: str | None) -> DiningTable | None:
    if table_id is not None:
        return db.get(DiningTable, table_id)
    if label:
        return db.scalar(select(DiningTable).where(DiningTable.label == label))
    return None


def open_tasks(db: Session, *, table_id: int | None = None, order_id: int | None = None,
               types: set[str] | None = None) -> list[Task]:
    q = select(Task).where(Task.status.in_(OPEN_TASK_STATUSES))
    if table_id is not None:
        q = q.where(Task.table_id == table_id)
    if order_id is not None:
        q = q.where(Task.order_id == order_id)
    if types:
        q = q.where(Task.type.in_(types))
    return list(db.scalars(q.order_by(Task.created_at)))


def create_task(db: Session, *, type: TaskType, title: str, now: datetime, priority: Priority,
                due_s: int | None, detail: str = "", table: DiningTable | None = None,
                order_id: int | None = None, source: str = "ai", staff_id: int | None = None) -> Task:
    task = Task(
        type=type, title=title, detail=detail, priority=priority, source=source,
        table_id=table.id if table else None, order_id=order_id,
        created_at=now, due_at=now + timedelta(seconds=due_s) if due_s else None,
    )
    if staff_id:
        task.staff_id, task.assigned_at, task.status = staff_id, now, TaskStatus.ASSIGNED
    db.add(task)
    _emit_task(db, task)
    return task


def close_task(db: Session, task: Task, status: TaskStatus, at: datetime, *,
               note: str | None = None, verified_by: str | None = None) -> None:
    task.status = status
    task.closed_at = at
    if note is not None:
        task.verification_note = note
    if verified_by:
        task.verified_by = verified_by
    resolve_alerts(db, at, task_id=task.id)
    _emit_task(db, task)


def raise_alert(db: Session, *, key: str, kind: str, priority: Priority, title: str, message: str,
                now: datetime, table_id: int | None = None, task_id: int | None = None) -> Alert | None:
    exists = db.scalar(select(Alert.id).where(Alert.key == key, Alert.resolved_at.is_(None)))
    if exists:
        return None
    alert = Alert(key=key, kind=kind, priority=priority, title=title, message=message,
                  table_id=table_id, task_id=task_id, created_at=now)
    db.add(alert)
    db.flush()
    payload = alert_out(alert).model_dump(mode="json")
    emit(db, "alert", payload)
    queue_notification(db, payload)
    return alert


def resolve_alerts(db: Session, now: datetime, *, key: str | None = None, task_id: int | None = None) -> None:
    q = select(Alert).where(Alert.resolved_at.is_(None))
    if key is not None:
        q = q.where(Alert.key == key)
    elif task_id is not None:
        q = q.where(Alert.task_id == task_id)
    else:
        raise ValueError("resolve_alerts needs key or task_id")
    for alert in db.scalars(q):
        alert.resolved_at = now
        db.flush()
        emit(db, "alert", alert_out(alert).model_dump(mode="json"))


# --------------------------------------------------------------------------- observations

def handle_event(db: Session, ev: EventIn, now: datetime) -> None:
    ts = _aware(ev.ts, now)
    table = resolve_table(db, ev.table_id, ev.table)
    db.add(Observation(ts=ts, type=ev.type, camera_id=ev.camera_id,
                       table_id=table.id if table else None, data=ev.data))
    if ev.camera_id:
        _touch_camera(db, ev.camera_id, ts)

    handler = _HANDLERS.get(ev.type)
    if handler:
        handler(db, table, ev, ts)


def _touch_camera(db: Session, camera_id: str, ts: datetime) -> None:
    cam = db.get(Camera, camera_id)
    if cam is None:
        cam = Camera(id=camera_id, name=camera_id)
        db.add(cam)
    if cam.last_seen_at is None or ts > cam.last_seen_at:
        cam.last_seen_at = ts
    if not cam.online:
        cam.online = True
        resolve_alerts(db, ts, key=f"camera_offline:{camera_id}")
        db.flush()
        emit(db, "camera", camera_out(cam).model_dump(mode="json"))


def _on_occupied(db: Session, table: DiningTable | None, ev: EventIn, ts: datetime) -> None:
    if table is None or table.status == TableStatus.OUT_OF_SERVICE:
        return
    party = int(ev.data.get("party_size", 0) or 0)
    if table.status == TableStatus.OCCUPIED:
        seating = db.get(Seating, table.current_seating_id) if table.current_seating_id else None
        if seating and party and party != seating.party_size:
            seating.party_size = party
            _emit_table(db, table)
        return

    if table.status == TableStatus.NEEDS_CLEANING:
        for t in open_tasks(db, table_id=table.id, types={TaskType.CLEAN_TABLE}):
            close_task(db, t, TaskStatus.CANCELLED, ts, note="Table was re-occupied before cleaning was verified.")
        raise_alert(db, key=f"seated_uncleaned:table:{table.id}:{int(ts.timestamp())}", kind="seated_uncleaned",
                    priority=Priority.MEDIUM, title=f"Table {table.label} seated before cleaning",
                    message="New customers sat down before the table was cleaned and verified.",
                    now=ts, table_id=table.id)

    seating = Seating(table_id=table.id, party_size=party, seated_at=ts)
    db.add(seating)
    db.flush()
    table.current_seating_id = seating.id
    set_table_status(db, table, TableStatus.OCCUPIED, ts)


def _on_vacated(db: Session, table: DiningTable | None, ev: EventIn, ts: datetime) -> None:
    if table is None or table.status != TableStatus.OCCUPIED:
        return
    if table.current_seating_id:
        seating = db.get(Seating, table.current_seating_id)
        if seating:
            seating.left_at = ts
    for t in open_tasks(db, table_id=table.id, types={TaskType.ASSIST_CUSTOMER, TaskType.ATTEND_TABLE}):
        close_task(db, t, TaskStatus.CANCELLED, ts, note="Customers left the table.")
    table.current_seating_id = None
    set_table_status(db, table, TableStatus.NEEDS_CLEANING, ts)
    create_task(
        db, type=TaskType.CLEAN_TABLE, title=f"Clean table {table.label}",
        detail=f"Customers left at {_hhmm(ts)}. Clear dishes and wipe the table.",
        table=table, priority=Priority.MEDIUM, due_s=settings.clean_due_s, now=ts,
    )


def _on_attended(db: Session, table: DiningTable | None, ev: EventIn, ts: datetime) -> None:
    if table is None:
        return
    if table.status == TableStatus.OCCUPIED and table.current_seating_id:
        seating = db.get(Seating, table.current_seating_id)
        if seating and seating.first_attended_at is None:
            seating.first_attended_at = ts
            _emit_table(db, table)
    for t in open_tasks(db, table_id=table.id, types={TaskType.ASSIST_CUSTOMER, TaskType.ATTEND_TABLE}):
        if t.created_at <= ts:
            secs = int((ts - t.created_at).total_seconds())
            close_task(db, t, TaskStatus.VERIFIED, ts, verified_by="ai",
                       note=f"Camera observed a staff visit at the table {secs}s after the request.")


def _on_surface(db: Session, table: DiningTable | None, ev: EventIn, ts: datetime) -> None:
    if table is None:
        return
    table.surface_items = int(ev.data.get("items", 0) or 0)
    table.surface_seen_at = ts
    _emit_table(db, table)
    # Fresh evidence: re-check pending verifications for this table immediately.
    for t in open_tasks(db, table_id=table.id, types={TaskType.CLEAN_TABLE}):
        if t.status == TaskStatus.AWAITING_VERIFICATION:
            try_verify(db, t, ts)


def _on_hand_raised(db: Session, table: DiningTable | None, ev: EventIn, ts: datetime) -> None:
    # A raised hand at an empty table is almost certainly a false positive.
    if table is None or table.status != TableStatus.OCCUPIED:
        return
    if open_tasks(db, table_id=table.id, types={TaskType.ASSIST_CUSTOMER}):
        return
    create_task(
        db, type=TaskType.ASSIST_CUSTOMER, title=f"Table {table.label} – customer needs assistance",
        detail="Customer raised a hand to request service.", table=table,
        priority=Priority.HIGH, due_s=settings.assist_response_s, now=ts,
    )


def _on_people_count(db: Session, table: DiningTable | None, ev: EventIn, ts: datetime) -> None:
    last = db.scalar(select(func.max(OccupancySample.ts)))
    if last and (ts - last).total_seconds() < 30:
        return
    occupied = db.scalar(select(func.count()).select_from(DiningTable)
                         .where(DiningTable.status == TableStatus.OCCUPIED)) or 0
    db.add(OccupancySample(ts=ts, people_inside=int(ev.data.get("inside", 0) or 0), occupied_tables=occupied))


_HANDLERS = {
    "table.occupied": _on_occupied,
    "table.vacated": _on_vacated,
    "table.attended": _on_attended,
    "table.surface": _on_surface,
    "service.hand_raised": _on_hand_raised,
    "people.count": _on_people_count,
}


# --------------------------------------------------------------------------- AI verification

def _latest_surface(db: Session, table_id: int, since: datetime) -> Observation | None:
    return db.scalar(
        select(Observation)
        .where(Observation.type == "table.surface", Observation.table_id == table_id, Observation.ts >= since)
        .order_by(Observation.ts.desc()).limit(1)
    )


def _visit_between(db: Session, table_id: int, start: datetime, end: datetime) -> Observation | None:
    return db.scalar(
        select(Observation)
        .where(Observation.type == "table.attended", Observation.table_id == table_id,
               Observation.ts >= start, Observation.ts <= end)
        .order_by(Observation.ts.desc()).limit(1)
    )


def try_verify(db: Session, task: Task, now: datetime) -> None:
    """Decide verified / failed / uncertain from camera evidence, or keep waiting."""
    if task.status != TaskStatus.AWAITING_VERIFICATION or task.completed_at is None:
        return
    grace = timedelta(seconds=settings.verify_grace_s)
    window_over = (now - task.completed_at).total_seconds() >= settings.verify_window_s
    done_at = task.completed_at

    if task.type == TaskType.CLEAN_TABLE and task.table_id:
        surface = _latest_surface(db, task.table_id, task.created_at)
        visit = _visit_between(db, task.table_id, task.created_at, max(now, done_at) )
        fresh = surface is not None and surface.ts >= done_at - grace
        if fresh:
            items = int(surface.data.get("items", 0) or 0)
            if items > 0:
                return _verification_failed(db, task, now, f"Camera still detects {items} item(s) on the table surface.")
            if visit:
                return _verified(db, task, now, f"Camera shows a clear surface and a staff visit at {_hhmm(visit.ts)}.")
            return _uncertain(db, task, now, "Surface looks clear but no staff visit was observed. Please check manually.")
        if window_over:
            return _uncertain(db, task, now, "No fresh camera view of the table after completion. Please check manually.")
        return

    if task.type in (TaskType.ASSIST_CUSTOMER, TaskType.ATTEND_TABLE) and task.table_id:
        visit = _visit_between(db, task.table_id, task.created_at, max(now, done_at))
        if visit:
            return _verified(db, task, now, f"Camera observed a staff visit at {_hhmm(visit.ts)}.")
        if window_over:
            return _uncertain(db, task, now, "No staff visit to the table was observed. Please check manually.")
        return

    if task.type == TaskType.DELIVER_ORDER:
        order = db.get(Order, task.order_id) if task.order_id else None
        if order and order.status == OrderStatus.DELIVERED:
            return _verified(db, task, now, "POS reports the order as delivered.", by="pos")
        if task.table_id:
            visit = _visit_between(db, task.table_id, task.created_at, max(now, done_at))
            if visit:
                return _verified(db, task, now, f"Camera observed a staff visit at {_hhmm(visit.ts)} after the order was ready.")
        if window_over:
            return _uncertain(db, task, now, "No delivery evidence from camera or POS. Please check manually.")
        return

    # Not visually verifiable.
    close_task(db, task, TaskStatus.DONE, now)


def _verified(db: Session, task: Task, now: datetime, note: str, by: str = "ai") -> None:
    close_task(db, task, TaskStatus.VERIFIED, now, note=note, verified_by=by)
    _after_clean_confirmed(db, task, now)


def _after_clean_confirmed(db: Session, task: Task, now: datetime) -> None:
    if task.type == TaskType.CLEAN_TABLE and task.table_id:
        table = db.get(DiningTable, task.table_id)
        if table and table.status == TableStatus.NEEDS_CLEANING:
            set_table_status(db, table, TableStatus.VACANT, now)


def _verification_failed(db: Session, task: Task, now: datetime, note: str) -> None:
    task.status, task.verification_note, task.verified_by = TaskStatus.VERIFICATION_FAILED, note, "ai"
    _emit_task(db, task)
    label = _label(db, task.table_id)
    raise_alert(db, key=f"verify_failed:task:{task.id}", kind="verification_failed", priority=Priority.MEDIUM,
                title=f"Table {label}: task not verified", message=f"{task.title}. {note}",
                now=now, table_id=task.table_id, task_id=task.id)


def _uncertain(db: Session, task: Task, now: datetime, note: str) -> None:
    task.status, task.verification_note, task.verified_by = TaskStatus.VERIFICATION_UNCERTAIN, note, "ai"
    _emit_task(db, task)
    label = _label(db, task.table_id)
    raise_alert(db, key=f"verify_uncertain:task:{task.id}", kind="verification_uncertain", priority=Priority.LOW,
                title=f"Table {label}: manual check needed", message=f"{task.title}. {note}",
                now=now, table_id=task.table_id, task_id=task.id)


def _label(db: Session, table_id: int | None) -> str:
    t = db.get(DiningTable, table_id) if table_id else None
    return t.label if t else "?"


# --------------------------------------------------------------------------- counter commands

def assign_task(db: Session, task: Task, staff: Staff, now: datetime) -> None:
    if task.status not in (TaskStatus.PENDING, TaskStatus.ASSIGNED):
        raise DomainError(f"Cannot assign a task that is {task.status}.")
    task.staff_id, task.assigned_at, task.status = staff.id, now, TaskStatus.ASSIGNED
    _emit_task(db, task)


def complete_task(db: Session, task: Task, now: datetime) -> None:
    """Stage 1: staff confirms. Stage 2 (verification) runs now and on later ticks."""
    if task.status not in (TaskStatus.PENDING, TaskStatus.ASSIGNED):
        raise DomainError(f"Cannot complete a task that is {task.status}.")
    task.completed_at = now
    if task.type in VERIFIABLE:
        task.status = TaskStatus.AWAITING_VERIFICATION
        resolve_alerts(db, now, task_id=task.id)  # e.g. 'overdue' no longer applies
        _emit_task(db, task)
        try_verify(db, task, now)
    else:
        close_task(db, task, TaskStatus.DONE, now)


def review_task(db: Session, task: Task, decision: str, note: str, now: datetime) -> None:
    """Human decision on a failed/uncertain verification (human-in-the-loop)."""
    if task.status not in (TaskStatus.VERIFICATION_FAILED, TaskStatus.VERIFICATION_UNCERTAIN):
        raise DomainError("Only failed or uncertain verifications can be reviewed.")
    if decision == "confirm":
        text = f"{task.verification_note} Confirmed by counter after manual inspection. {note}".strip()
        close_task(db, task, TaskStatus.VERIFIED, now, note=text, verified_by="manual")
        _after_clean_confirmed(db, task, now)
    else:
        task.status = TaskStatus.ASSIGNED if task.staff_id else TaskStatus.PENDING
        task.completed_at = None
        task.verified_by = None
        task.verification_note = f"Sent back for redo: {task.verification_note} {note}".strip()
        due = settings.clean_due_s if task.type == TaskType.CLEAN_TABLE else settings.generic_task_due_s
        task.due_at = now + timedelta(seconds=due)
        resolve_alerts(db, now, task_id=task.id)
        _emit_task(db, task)


def cancel_task(db: Session, task: Task, now: datetime) -> None:
    if task.status not in OPEN_TASK_STATUSES:
        raise DomainError("Task is already closed.")
    close_task(db, task, TaskStatus.CANCELLED, now, note="Cancelled at the counter.")


def set_table_manual(db: Session, table: DiningTable, status: str, now: datetime) -> None:
    if status == TableStatus.VACANT:
        for t in open_tasks(db, table_id=table.id):
            close_task(db, t, TaskStatus.CANCELLED, now, note="Table manually reset to vacant at the counter.")
        if table.current_seating_id:
            s = db.get(Seating, table.current_seating_id)
            if s and s.left_at is None:
                s.left_at = now
            table.current_seating_id = None
    set_table_status(db, table, TableStatus(status), now)


# --------------------------------------------------------------------------- POS integration

def touch_integration(db: Session, name: str, ts: datetime) -> None:
    """Record that an integration (the POS feed) delivered data. Status only, no alerts."""
    rec = db.get(Integration, name)
    if rec is None:
        rec = Integration(id=name)
        db.add(rec)
    rec.last_seen_at, rec.online = ts, True
    db.flush()
    emit(db, "integration", integration_out(rec).model_dump(mode="json"))  # dashboard shows 'last update'


def upsert_order(db: Session, *, pos_ref: str, table: DiningTable | None, items: str, status: str,
                 sla_minutes: int | None, ts: datetime) -> Order:
    order = db.scalar(select(Order).where(Order.pos_ref == pos_ref))
    if order is None:
        order = Order(pos_ref=pos_ref, table_id=table.id if table else None, items=items,
                      sla_minutes=sla_minutes or settings.default_order_sla_min, placed_at=ts)
        db.add(order)
    else:
        if items:
            order.items = items
        if sla_minutes:
            order.sla_minutes = sla_minutes
    set_order_status(db, order, status, ts)
    return order


def set_order_status(db: Session, order: Order, status: str, ts: datetime) -> None:
    db.flush()  # ensure order.id exists for alert keys
    order.status = status
    if status in (OrderStatus.READY, OrderStatus.DELIVERED) and order.ready_at is None:
        order.ready_at = ts
    if status not in (OrderStatus.PLACED, OrderStatus.PREPARING):
        resolve_alerts(db, ts, key=f"order_delayed:order:{order.id}")
        for t in open_tasks(db, order_id=order.id, types={TaskType.CHECK_ORDER}):
            close_task(db, t, TaskStatus.DONE, ts, note="Kitchen marked the order ready.")
    if status == OrderStatus.DELIVERED:
        order.delivered_at = ts
        resolve_alerts(db, ts, key=f"deliver_overdue:order:{order.id}")
        for t in open_tasks(db, order_id=order.id, types={TaskType.DELIVER_ORDER}):
            close_task(db, t, TaskStatus.VERIFIED, ts, note="POS reports the order as delivered.", verified_by="pos")
    if status == OrderStatus.CANCELLED:
        for t in open_tasks(db, order_id=order.id):
            close_task(db, t, TaskStatus.CANCELLED, ts, note="Order cancelled in POS.")
        resolve_alerts(db, ts, key=f"deliver_overdue:order:{order.id}")
    _emit_order(db, order)


# --------------------------------------------------------------------------- time-based rules

def tick(db: Session, now: datetime) -> None:
    _check_cameras(db, now)
    _check_integrations(db, now)
    _check_assist(db, now)
    _check_seated_unattended(db, now)
    _check_overdue(db, now)
    for task in db.scalars(select(Task).where(Task.status == TaskStatus.AWAITING_VERIFICATION)):
        try_verify(db, task, now)
    _check_orders(db, now)


def _check_cameras(db: Session, now: datetime) -> None:
    stale = timedelta(seconds=settings.camera_stale_s)
    for cam in db.scalars(select(Camera).where(Camera.online.is_(True))):
        if cam.last_seen_at and now - cam.last_seen_at > stale:
            cam.online = False
            db.flush()
            emit(db, "camera", camera_out(cam).model_dump(mode="json"))
            raise_alert(db, key=f"camera_offline:{cam.id}", kind="camera_offline", priority=Priority.HIGH,
                        title=f"Camera {cam.name} offline",
                        message=f"No data from camera {cam.name} for over {settings.camera_stale_s}s. "
                                "Monitoring for its tables is paused.", now=now)


def _check_integrations(db: Session, now: datetime) -> None:
    stale = timedelta(seconds=settings.pos_stale_s)
    for rec in db.scalars(select(Integration).where(Integration.online.is_(True))):
        if rec.last_seen_at and now - rec.last_seen_at > stale:
            rec.online = False
            db.flush()
            emit(db, "integration", integration_out(rec).model_dump(mode="json"))


def _check_assist(db: Session, now: datetime) -> None:
    q = select(Task).where(Task.type == TaskType.ASSIST_CUSTOMER, Task.status.in_(
        (TaskStatus.PENDING, TaskStatus.ASSIGNED)), Task.due_at < now)
    for t in db.scalars(q):
        label = _label(db, t.table_id)
        raise_alert(db, key=f"assist_unattended:task:{t.id}", kind="assist_unattended", priority=Priority.HIGH,
                    title=f"Table {label} – customer needs assistance",
                    message=f"Customer raised hand. No staff response detected within {settings.assist_response_s}s.",
                    now=now, table_id=t.table_id, task_id=t.id)


def _check_seated_unattended(db: Session, now: datetime) -> None:
    limit = now - timedelta(seconds=settings.seated_unattended_s)
    q = (select(DiningTable, Seating).join(Seating, Seating.id == DiningTable.current_seating_id)
         .where(DiningTable.status == TableStatus.OCCUPIED, Seating.first_attended_at.is_(None),
                Seating.seated_at <= limit))
    for table, seating in db.execute(q):
        if open_tasks(db, table_id=table.id, types={TaskType.ATTEND_TABLE, TaskType.ASSIST_CUSTOMER}):
            continue
        # Only once per seating: skip if an attend task already existed for this stay.
        prior = db.scalar(select(Task.id).where(Task.table_id == table.id, Task.type == TaskType.ATTEND_TABLE,
                                                Task.created_at >= seating.seated_at))
        if prior:
            continue
        mins = max(1, int((now - seating.seated_at).total_seconds() // 60))
        task = create_task(db, type=TaskType.ATTEND_TABLE, title=f"Attend table {table.label}",
                           detail=f"Customers seated {mins} min ago with no staff visit yet.",
                           table=table, priority=Priority.HIGH, due_s=settings.assist_response_s, now=now)
        raise_alert(db, key=f"seated_unattended:task:{task.id}", kind="seated_unattended", priority=Priority.HIGH,
                    title=f"Table {table.label} – customers waiting",
                    message=f"Seated {mins} min with no staff visit detected.",
                    now=now, table_id=table.id, task_id=task.id)


def _check_overdue(db: Session, now: datetime) -> None:
    q = select(Task).where(Task.status.in_((TaskStatus.PENDING, TaskStatus.ASSIGNED)), Task.due_at < now,
                           Task.type.not_in((TaskType.ASSIST_CUSTOMER, TaskType.ATTEND_TABLE)))
    for t in db.scalars(q):
        who = ""
        if t.staff_id:
            s = db.get(Staff, t.staff_id)
            who = f" Assigned to {s.name}." if s else ""
        else:
            who = " Not yet assigned."
        raise_alert(db, key=f"task_overdue:task:{t.id}", kind="task_overdue", priority=Priority.MEDIUM,
                    title=f"Task overdue: {t.title}", message=f"Due at {_hhmm(t.due_at)}.{who}",
                    now=now, table_id=t.table_id, task_id=t.id)


def _check_orders(db: Session, now: datetime) -> None:
    active = db.scalars(select(Order).where(Order.status.in_((OrderStatus.PLACED, OrderStatus.PREPARING))))
    for o in active:
        late = (now - o.placed_at).total_seconds() / 60 - o.sla_minutes
        if late <= 0:
            continue
        label = _label(db, o.table_id)
        alert = raise_alert(db, key=f"order_delayed:order:{o.id}", kind="order_delayed", priority=Priority.HIGH,
                            title=f"Table {label} – order delayed",
                            message=f"Order {o.pos_ref} is past its {o.sla_minutes} min preparation target.",
                            now=now, table_id=o.table_id)
        if alert and not open_tasks(db, order_id=o.id, types={TaskType.CHECK_ORDER}):
            create_task(db, type=TaskType.CHECK_ORDER, title=f"Check kitchen on order {o.pos_ref}",
                        detail=f"Table {label}. Update the customers on the delay.",
                        table=db.get(DiningTable, o.table_id) if o.table_id else None,
                        order_id=o.id, priority=Priority.MEDIUM, due_s=settings.generic_task_due_s,
                        now=now, source="pos")

    ready = db.scalars(select(Order).where(Order.status == OrderStatus.READY, Order.ready_at <= now - timedelta(
        seconds=settings.deliver_due_s)))
    for o in ready:
        if open_tasks(db, order_id=o.id, types={TaskType.DELIVER_ORDER}):
            continue
        label = _label(db, o.table_id)
        task = create_task(db, type=TaskType.DELIVER_ORDER, title=f"Deliver order {o.pos_ref} to table {label}",
                           detail=f"Food has been waiting at the pass since {_hhmm(o.ready_at)}.",
                           table=db.get(DiningTable, o.table_id) if o.table_id else None, order_id=o.id,
                           priority=Priority.HIGH, due_s=settings.assist_response_s, now=now, source="pos")
        raise_alert(db, key=f"deliver_overdue:order:{o.id}", kind="delivery_overdue", priority=Priority.HIGH,
                    title=f"Table {label} – food delivery overdue",
                    message=f"Order {o.pos_ref} ready for over {settings.deliver_due_s}s and not delivered.",
                    now=now, table_id=o.table_id, task_id=task.id)

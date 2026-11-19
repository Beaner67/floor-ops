from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db import Base, make_engine
from app.engine import ops
from app.models import Alert, DiningTable, Order, Seating, Staff, Task, TaskStatus, TaskType
from app.schemas import EventIn
from app.seed import seed

T0 = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)


def at(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


@pytest.fixture
def db():
    eng = make_engine("sqlite://")
    Base.metadata.create_all(eng)
    s = sessionmaker(bind=eng, expire_on_commit=False)()
    seed(s)
    yield s
    s.close()


def ev(db, type_, table="3", t=0, **data):
    ops.handle_event(db, EventIn(type=type_, table=table, camera_id="cam-1", ts=at(t), data=data), at(t))
    db.flush()


def table(db, label="3") -> DiningTable:
    return db.scalar(select(DiningTable).where(DiningTable.label == label))


def tasks(db, type_=None) -> list[Task]:
    q = select(Task).order_by(Task.id)
    if type_:
        q = q.where(Task.type == type_)
    return list(db.scalars(q))


def open_alert_kinds(db) -> set[str]:
    return {a.kind for a in db.scalars(select(Alert).where(Alert.resolved_at.is_(None)))}


def staff(db) -> Staff:
    return db.scalar(select(Staff).limit(1))


def seat_and_leave(db):
    ev(db, "table.occupied", t=0, party_size=3)
    ev(db, "table.attended", t=20)
    ev(db, "table.vacated", t=600)


def test_party_leaving_creates_cleaning_task(db):
    seat_and_leave(db)
    assert table(db).status == "needs_cleaning"
    [clean] = tasks(db, TaskType.CLEAN_TABLE)
    assert clean.status == TaskStatus.PENDING and clean.priority == "medium"
    seating = db.scalar(select(Seating))
    assert seating.party_size == 3 and seating.left_at == at(600)
    assert (seating.first_attended_at - seating.seated_at).total_seconds() == 20


def test_cleaning_verified_with_visit_and_clear_surface(db):
    seat_and_leave(db)
    [clean] = tasks(db, TaskType.CLEAN_TABLE)
    ops.assign_task(db, clean, staff(db), at(610))
    ev(db, "table.attended", t=640)          # busser at the table
    ev(db, "table.surface", t=660, items=0)  # surface now clear
    ops.complete_task(db, clean, at(665))
    assert clean.status == TaskStatus.VERIFIED and clean.verified_by == "ai"
    assert table(db).status == "vacant"


def test_cleaning_verification_fails_when_items_remain(db):
    seat_and_leave(db)
    [clean] = tasks(db, TaskType.CLEAN_TABLE)
    ops.assign_task(db, clean, staff(db), at(610))
    ops.complete_task(db, clean, at(620))
    assert clean.status == TaskStatus.AWAITING_VERIFICATION
    ev(db, "table.surface", t=625, items=2)
    assert clean.status == TaskStatus.VERIFICATION_FAILED
    assert table(db).status == "needs_cleaning"
    assert "verification_failed" in open_alert_kinds(db)

    # Counter sends it back, staff redoes it, camera confirms.
    ops.review_task(db, clean, "redo", "", at(630))
    assert clean.status == TaskStatus.ASSIGNED and "verification_failed" not in open_alert_kinds(db)
    ev(db, "table.attended", t=650)
    ev(db, "table.surface", t=660, items=0)
    ops.complete_task(db, clean, at(661))
    assert clean.status == TaskStatus.VERIFIED and table(db).status == "vacant"


def test_cleaning_uncertain_without_camera_evidence_then_manual_confirm(db):
    seat_and_leave(db)
    [clean] = tasks(db, TaskType.CLEAN_TABLE)
    ops.complete_task(db, clean, at(620))
    ops.tick(db, at(620 + settings.verify_window_s - 1))
    assert clean.status == TaskStatus.AWAITING_VERIFICATION
    ops.tick(db, at(620 + settings.verify_window_s + 1))
    assert clean.status == TaskStatus.VERIFICATION_UNCERTAIN
    ops.review_task(db, clean, "confirm", "checked in person", at(700))
    assert clean.status == TaskStatus.VERIFIED and clean.verified_by == "manual"
    assert table(db).status == "vacant"


def test_raised_hand_escalates_then_resolves_on_staff_visit(db):
    ev(db, "table.occupied", t=0)
    ev(db, "service.hand_raised", t=100)
    ev(db, "service.hand_raised", t=105)  # duplicate gesture -> still one task
    [assist] = tasks(db, TaskType.ASSIST_CUSTOMER)
    assert assist.priority == "high"

    ops.tick(db, at(100 + settings.assist_response_s - 1))
    assert "assist_unattended" not in open_alert_kinds(db)
    ops.tick(db, at(100 + settings.assist_response_s + 1))
    ops.tick(db, at(100 + settings.assist_response_s + 5))  # idempotent
    assert db.scalar(select(Alert).where(Alert.kind == "assist_unattended")) is not None
    assert len(list(db.scalars(select(Alert).where(Alert.kind == "assist_unattended")))) == 1

    ev(db, "table.attended", t=200)
    assert assist.status == TaskStatus.VERIFIED
    assert (assist.closed_at - assist.created_at).total_seconds() == 100
    assert "assist_unattended" not in open_alert_kinds(db)


def test_hand_raise_at_empty_table_is_ignored(db):
    ev(db, "service.hand_raised", t=0)
    assert tasks(db) == []


def test_seated_without_any_visit_creates_attend_task_once(db):
    ev(db, "table.occupied", t=0)
    ops.tick(db, at(settings.seated_unattended_s + 1))
    ops.tick(db, at(settings.seated_unattended_s + 10))
    assert len(tasks(db, TaskType.ATTEND_TABLE)) == 1
    assert "seated_unattended" in open_alert_kinds(db)
    ev(db, "table.attended", t=settings.seated_unattended_s + 20)
    assert tasks(db, TaskType.ATTEND_TABLE)[0].status == TaskStatus.VERIFIED
    assert "seated_unattended" not in open_alert_kinds(db)
    ops.tick(db, at(settings.seated_unattended_s * 3))
    assert len(tasks(db, TaskType.ATTEND_TABLE)) == 1


def test_reoccupied_before_cleaning_cancels_clean_task(db):
    seat_and_leave(db)
    ev(db, "table.occupied", t=700)
    assert tasks(db, TaskType.CLEAN_TABLE)[0].status == TaskStatus.CANCELLED
    assert table(db).status == "occupied"
    assert "seated_uncleaned" in open_alert_kinds(db)


def test_order_delay_and_delivery_flow(db):
    t3 = table(db)
    order = ops.upsert_order(db, pos_ref="A100", table=t3, items="2x Biryani", status="placed",
                             sla_minutes=10, ts=at(0))
    ops.tick(db, at(9 * 60))
    assert "order_delayed" not in open_alert_kinds(db)
    ops.tick(db, at(11 * 60))
    assert "order_delayed" in open_alert_kinds(db)
    assert len(tasks(db, TaskType.CHECK_ORDER)) == 1

    ops.set_order_status(db, order, "ready", at(12 * 60))
    assert "order_delayed" not in open_alert_kinds(db)
    assert tasks(db, TaskType.CHECK_ORDER)[0].status == TaskStatus.DONE

    ops.tick(db, at(12 * 60 + settings.deliver_due_s + 1))
    [deliver] = tasks(db, TaskType.DELIVER_ORDER)
    assert "delivery_overdue" in open_alert_kinds(db)
    ops.set_order_status(db, order, "delivered", at(15 * 60))
    assert deliver.status == TaskStatus.VERIFIED and deliver.verified_by == "pos"
    assert "delivery_overdue" not in open_alert_kinds(db)
    assert db.get(Order, order.id).delivered_at == at(15 * 60)


def test_camera_offline_alert_and_recovery(db):
    ev(db, "camera.heartbeat", table=None, t=0)
    ops.tick(db, at(settings.camera_stale_s + 5))
    assert "camera_offline" in open_alert_kinds(db)
    ev(db, "camera.heartbeat", table=None, t=settings.camera_stale_s + 10)
    assert "camera_offline" not in open_alert_kinds(db)


def test_manual_task_completes_without_verification(db):
    task = ops.create_task(db, type=TaskType.GENERAL, title="Refill napkins", now=at(0),
                           priority="low", due_s=300, source="manual")
    ops.complete_task(db, task, at(30))
    assert task.status == TaskStatus.DONE


def test_cannot_complete_closed_task(db):
    task = ops.create_task(db, type=TaskType.GENERAL, title="x", now=at(0), priority="low", due_s=None)
    ops.cancel_task(db, task, at(1))
    with pytest.raises(ops.DomainError):
        ops.complete_task(db, task, at(2))


def test_pos_feed_status_goes_idle_when_quiet(db):
    from app.models import Integration
    ops.touch_integration(db, "pos", at(0))
    assert db.get(Integration, "pos").online
    ops.tick(db, at(settings.pos_stale_s - 1))
    assert db.get(Integration, "pos").online
    ops.tick(db, at(settings.pos_stale_s + 1))
    assert not db.get(Integration, "pos").online
    assert "pos" not in str(open_alert_kinds(db))  # status only, never an alert

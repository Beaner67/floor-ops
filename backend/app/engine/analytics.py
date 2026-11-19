"""Operational reports. Prototype-scale: aggregates in Python over the window.
Swap for SQL aggregates / materialised views once data volume warrants it.

Staff figures are task counts and durations only. There are no scores or rankings:
the system measures processes, not people.
"""
from collections import defaultdict
from datetime import datetime, timedelta
from statistics import mean

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    OPEN_TASK_STATUSES,
    Observation,
    OccupancySample,
    Order,
    OrderStatus,
    Seating,
    Staff,
    Task,
    TaskStatus,
    TaskType,
)


def _avg(values: list[float]) -> float | None:
    return round(mean(values), 1) if values else None


def report(db: Session, now: datetime, hours: int = 24) -> dict:
    since = now - timedelta(hours=hours)

    seatings = list(db.scalars(select(Seating).where(Seating.seated_at >= since)))
    wait = [(s.first_attended_at - s.seated_at).total_seconds() for s in seatings if s.first_attended_at]
    stay = [(s.left_at - s.seated_at).total_seconds() for s in seatings if s.left_at]

    tasks = list(db.scalars(select(Task).where(Task.created_at >= since)))
    assist = [t for t in tasks if t.type == TaskType.ASSIST_CUSTOMER and t.status == TaskStatus.VERIFIED and t.closed_at]
    clean = [t for t in tasks if t.type == TaskType.CLEAN_TABLE and t.status == TaskStatus.VERIFIED and t.closed_at]
    open_now = db.scalar(select(func.count()).select_from(Task).where(Task.status.in_(OPEN_TASK_STATUSES))) or 0
    overdue_now = db.scalar(select(func.count()).select_from(Task).where(
        Task.status.in_((TaskStatus.PENDING, TaskStatus.ASSIGNED)), Task.due_at < now)) or 0

    verification = defaultdict(int)
    for t in tasks:
        if t.status in (TaskStatus.VERIFIED, TaskStatus.VERIFICATION_FAILED, TaskStatus.VERIFICATION_UNCERTAIN):
            verification[f"{t.status}:{t.verified_by or 'ai'}"] += 1

    staff_rows = []
    for s in db.scalars(select(Staff).order_by(Staff.name)):
        mine = [t for t in tasks if t.staff_id == s.id]
        finished = [t for t in mine if t.completed_at and t.assigned_at]
        staff_rows.append({
            "staff_id": s.id, "name": s.name,
            "assigned": len(mine),
            "completed": len([t for t in mine if t.completed_at]),
            "verified": len([t for t in mine if t.status == TaskStatus.VERIFIED]),
            "needs_review": len([t for t in mine if t.status in (TaskStatus.VERIFICATION_FAILED,
                                                                  TaskStatus.VERIFICATION_UNCERTAIN)]),
            "avg_completion_s": _avg([(t.completed_at - t.assigned_at).total_seconds() for t in finished]),
        })

    orders = list(db.scalars(select(Order).where(Order.placed_at >= since)))
    prep = [(o.ready_at - o.placed_at).total_seconds() for o in orders if o.ready_at]
    deliver = [(o.delivered_at - o.ready_at).total_seconds() for o in orders if o.delivered_at and o.ready_at]
    delayed = [o for o in orders if (o.ready_at or now) - o.placed_at > timedelta(minutes=o.sla_minutes)
               and o.status != OrderStatus.CANCELLED]

    # Hourly occupancy and arrivals (local time buckets for display).
    by_hour_people: dict[int, list[int]] = defaultdict(list)
    for smp in db.scalars(select(OccupancySample).where(OccupancySample.ts >= since)):
        by_hour_people[smp.ts.astimezone().hour].append(smp.people_inside)
    by_hour_seatings: dict[int, int] = defaultdict(int)
    for s in seatings:
        by_hour_seatings[s.seated_at.astimezone().hour] += 1
    hourly = [{"hour": h, "avg_people": _avg(by_hour_people.get(h, [])) or 0, "seatings": by_hour_seatings.get(h, 0)}
              for h in range(24)]
    peak = max(hourly, key=lambda r: (r["avg_people"], r["seatings"]))
    entries = db.scalar(select(func.count()).select_from(Observation).where(
        Observation.type == "entrance.enter", Observation.ts >= since)) or 0

    return {
        "window_hours": hours,
        "generated_at": now,
        "customers": {
            "seatings": len(seatings),
            "entries_counted": entries,
            "avg_wait_for_first_visit_s": _avg(wait),
            "avg_stay_s": _avg(stay),
        },
        "service": {
            "assist_requests": len([t for t in tasks if t.type == TaskType.ASSIST_CUSTOMER]),
            "avg_assist_response_s": _avg([(t.closed_at - t.created_at).total_seconds() for t in assist]),
            "unattended_alerts": len([t for t in tasks if t.type == TaskType.ATTEND_TABLE]),
        },
        "cleaning": {
            "tables_cleaned": len(clean),
            "avg_clean_duration_s": _avg([(t.closed_at - t.created_at).total_seconds() for t in clean]),
        },
        "tasks": {
            "created": len(tasks),
            "open_now": open_now,
            "overdue_now": overdue_now,
            "verification": dict(verification),
        },
        "orders": {
            "count": len(orders),
            "delayed": len(delayed),
            "avg_prep_s": _avg(prep),
            "avg_ready_to_table_s": _avg(deliver),
        },
        "staff": staff_rows,
        "hourly": hourly,
        "peak_hour": peak["hour"] if (peak["avg_people"] or peak["seatings"]) else None,
    }

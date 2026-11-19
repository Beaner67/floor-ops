"""Machine-facing endpoints: camera/vision workers and POS adapters."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import now, require_device_key
from ..engine import ops
from ..engine.lock import write_lock
from ..schemas import EventIn, OrderOut, PosOrderIn, PosStatusIn
from ..serialize import order_out
from sqlalchemy import select
from ..models import Order

router = APIRouter(prefix="/api", tags=["ingest"], dependencies=[Depends(require_device_key)])


@router.post("/events", status_code=202)
def ingest_events(events: EventIn | list[EventIn], db: Session = Depends(get_db)) -> dict:
    batch = events if isinstance(events, list) else [events]
    with write_lock:
        t = now()
        for ev in batch:
            ops.handle_event(db, ev, t)
        db.commit()
    return {"accepted": len(batch)}


@router.post("/pos/orders", response_model=OrderOut)
def pos_upsert_order(body: PosOrderIn, db: Session = Depends(get_db)):
    """Generic POS webhook. A vendor-specific adapter maps its payload to this shape."""
    with write_lock:
        t = now()
        table = ops.resolve_table(db, body.table_id, body.table)
        order = ops.upsert_order(db, pos_ref=body.pos_ref, table=table, items=body.items, status=body.status,
                                 sla_minutes=body.sla_minutes, ts=body.ts or t)
        ops.touch_integration(db, "pos", t)
        db.commit()
        return order_out(db, order)


@router.post("/pos/orders/{pos_ref}/status", response_model=OrderOut)
def pos_order_status(pos_ref: str, body: PosStatusIn, db: Session = Depends(get_db)):
    with write_lock:
        order = db.scalar(select(Order).where(Order.pos_ref == pos_ref))
        if order is None:
            raise HTTPException(404, "unknown order")
        t = now()
        ops.set_order_status(db, order, body.status, body.ts or t)
        ops.touch_integration(db, "pos", t)
        db.commit()
        return order_out(db, order)

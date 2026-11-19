from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import now
from ..engine.analytics import report

router = APIRouter(prefix="/api", tags=["reports"])


@router.get("/analytics")
def analytics(hours: int = Query(24, ge=1, le=24 * 31), db: Session = Depends(get_db)) -> dict:
    return report(db, now(), hours)

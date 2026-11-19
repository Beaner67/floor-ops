"""Demo restaurant: 8 tables across 2 cameras, 4 staff."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Camera, DiningTable, Staff

TABLES = [
    # label, capacity, camera, x%, y%
    ("1", 2, "cam-1", 14, 22), ("2", 2, "cam-1", 36, 22), ("3", 4, "cam-1", 58, 22), ("4", 4, "cam-1", 82, 22),
    ("5", 4, "cam-2", 14, 68), ("6", 6, "cam-2", 40, 68), ("7", 4, "cam-2", 64, 68), ("8", 2, "cam-2", 86, 68),
]
STAFF = [("Asha", "server"), ("Rahul", "server"), ("Meera", "server"), ("Vikram", "busser")]


def seed(db: Session) -> None:
    if db.scalar(select(DiningTable.id).limit(1)) is not None:
        return
    db.add_all([Camera(id="cam-1", name="Dining – window side"), Camera(id="cam-2", name="Dining – back")])
    for label, cap, cam, x, y in TABLES:
        db.add(DiningTable(label=label, capacity=cap, camera_id=cam, pos_x=x, pos_y=y))
    for name, role in STAFF:
        db.add(Staff(name=name, role=role))
    db.commit()

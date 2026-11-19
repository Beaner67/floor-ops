import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

from .bus import bus
from .config import settings
from .db import Base, SessionLocal, engine
from .deps import now
from .engine import ops
from .engine.lock import write_lock
from .routers import counter, ingest, reports
from .seed import seed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")


def _tick_once() -> None:
    with write_lock:
        db = SessionLocal()
        try:
            ops.tick(db, now())
            db.commit()
        except Exception:
            db.rollback()
            log.exception("tick failed")
        finally:
            db.close()


async def _ticker() -> None:
    while True:
        await run_in_threadpool(_tick_once)
        await asyncio.sleep(settings.tick_interval_s)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Prototype: create schema directly. Production: Alembic migrations.
    Base.metadata.create_all(engine)
    if settings.seed_demo_data:
        with SessionLocal() as db:
            seed(db)
    bus.bind(asyncio.get_running_loop())
    tasks = [asyncio.create_task(bus.run()), asyncio.create_task(_ticker())]
    yield
    for t in tasks:
        t.cancel()


app = FastAPI(title="Restaurant Operations Intelligence", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])
app.include_router(ingest.router)
app.include_router(counter.router)
app.include_router(reports.router)


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await bus.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # keepalive pings from the client
    except WebSocketDisconnect:
        bus.disconnect(websocket)

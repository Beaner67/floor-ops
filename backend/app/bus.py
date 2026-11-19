"""Transactional outbox -> WebSocket broadcast.

Engine code runs in worker threads and calls `emit(db, ...)`. Messages are held
on the session and only published *after* the transaction commits, so the
dashboard never sees state that was rolled back.
"""
import asyncio
import logging
from typing import Any

from fastapi import WebSocket
from sqlalchemy import event
from sqlalchemy.orm import Session

from . import notifier

log = logging.getLogger(__name__)


class Bus:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue: asyncio.Queue | None = None
        self._clients: set[WebSocket] = set()

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._queue = asyncio.Queue()

    def publish(self, msg: dict[str, Any]) -> None:
        if self._loop and self._queue is not None:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, msg)

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    async def run(self) -> None:
        assert self._queue is not None
        while True:
            msg = await self._queue.get()
            for ws in list(self._clients):
                try:
                    await ws.send_json(msg)
                except Exception:  # client went away mid-send
                    self.disconnect(ws)


bus = Bus()


def emit(db: Session, kind: str, data: dict[str, Any]) -> None:
    db.info.setdefault("outbox", []).append({"type": kind, "data": data})


def queue_notification(db: Session, alert: dict[str, Any]) -> None:
    db.info.setdefault("notify", []).append(alert)


@event.listens_for(Session, "after_commit")
def _after_commit(session: Session) -> None:
    for msg in session.info.pop("outbox", []):
        bus.publish(msg)
    for alert in session.info.pop("notify", []):
        notifier.send(alert)


@event.listens_for(Session, "after_rollback")
def _after_rollback(session: Session) -> None:
    session.info.pop("outbox", None)
    session.info.pop("notify", None)

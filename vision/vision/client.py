"""Buffered event sender. Survives backend restarts without losing recent events."""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from datetime import datetime, timezone

import requests

log = logging.getLogger("client")


class EventClient:
    def __init__(self, base_url: str, device_key: str = "", max_buffer: int = 5000):
        self.url = base_url.rstrip("/") + "/api/events"
        self.headers = {"X-Device-Key": device_key} if device_key else {}
        self._buf: deque[dict] = deque(maxlen=max_buffer)
        self._lock = threading.Lock()
        threading.Thread(target=self._loop, daemon=True).start()

    def send(self, camera_id: str, event: dict) -> None:
        event = {**event, "camera_id": camera_id, "ts": datetime.now(timezone.utc).isoformat()}
        with self._lock:
            self._buf.append(event)

    def _loop(self) -> None:
        while True:
            time.sleep(0.5)
            with self._lock:
                batch = list(self._buf)
            if not batch:
                continue
            try:
                r = requests.post(self.url, json=batch, headers=self.headers, timeout=5)
                r.raise_for_status()
                with self._lock:
                    for _ in batch:
                        self._buf.popleft()
            except requests.RequestException as exc:
                log.warning("backend unreachable (%s); %d events buffered", exc, len(batch))
                time.sleep(2)

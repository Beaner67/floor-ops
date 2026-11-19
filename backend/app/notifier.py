"""Manager phone notifications.

Every alert reaches the manager dashboard over WebSocket. If RI_NOTIFY_URL is set
(an ntfy.sh-compatible topic URL), alerts at or above RI_NOTIFY_MIN_PRIORITY are
also pushed so the manager's phone buzzes with the dashboard closed. Sending
happens on a daemon thread so a slow network never blocks the engine.
"""
import logging
import threading
from typing import Any

import httpx

from .config import settings

log = logging.getLogger("notifier")
_RANK = {"low": 0, "medium": 1, "high": 2}
_NTFY_PRIORITY = {"low": "2", "medium": "3", "high": "5"}


def send(alert: dict[str, Any]) -> None:
    log.info("ALERT [%s] %s - %s", alert["priority"], alert["title"], alert["message"])
    if not settings.notify_url:
        return
    if _RANK[alert["priority"]] < _RANK.get(settings.notify_min_priority, 1):
        return
    threading.Thread(target=_push, args=(alert,), daemon=True).start()


def _push(alert: dict[str, Any]) -> None:
    try:
        httpx.post(
            settings.notify_url,
            content=alert["message"].encode(),
            headers={
                "Title": alert["title"],
                "Priority": _NTFY_PRIORITY[alert["priority"]],
                "Tags": "rotating_light" if alert["priority"] == "high" else "bell",
            },
            timeout=5,
        )
    except httpx.HTTPError as exc:
        log.warning("push notification failed: %s", exc)

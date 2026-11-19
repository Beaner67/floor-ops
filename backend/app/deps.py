from datetime import datetime, timezone

from fastapi import Header, HTTPException

from .config import settings


def now() -> datetime:
    return datetime.now(timezone.utc)


def require_device_key(x_device_key: str = Header(default="")) -> None:
    """Cameras / POS adapters authenticate with a shared key."""
    if settings.device_key and x_device_key != settings.device_key:
        raise HTTPException(status_code=401, detail="invalid device key")

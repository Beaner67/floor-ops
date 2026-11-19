"""Runtime configuration.

Every operational threshold lives here so it can be tuned per restaurant
(env vars prefixed with RI_, or a backend/.env file). Defaults are short so a
live demo shows escalations within a minute or two; raise them for real service.
"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RI_", env_file=BACKEND_DIR / ".env", extra="ignore")

    database_url: str = f"sqlite:///{(BACKEND_DIR / 'restaurant.db').as_posix()}"
    # Shared secret that camera/vision workers and POS adapters send as X-Device-Key.
    # Empty string disables the check (local development only).
    device_key: str = ""
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # --- Service thresholds (seconds) ---
    assist_response_s: int = 60        # raised hand -> staff visit expected within
    seated_unattended_s: int = 120     # seated party with no staff visit at all
    clean_due_s: int = 240             # table vacated -> cleaned & verified
    generic_task_due_s: int = 300      # manual tasks
    deliver_due_s: int = 90            # order ready -> delivered to table
    default_order_sla_min: int = 15    # placed -> ready, if POS sends none

    # --- AI verification ---
    verify_window_s: int = 30          # wait this long for camera evidence after staff confirms
    verify_grace_s: int = 10           # evidence this close before confirmation still counts

    # --- Infrastructure health ---
    camera_stale_s: int = 60
    pos_stale_s: int = 300           # POS feed shown as idle after this long without data
    tick_interval_s: float = 2.0

    # --- Manager notifications ---
    # Optional ntfy.sh-compatible topic URL (e.g. https://ntfy.sh/<random-topic>) for phone push.
    notify_url: str = ""
    notify_min_priority: str = "medium"

    seed_demo_data: bool = True


settings = Settings()

"""Lightweight settings loaded from backend/.env (or the process environment)."""
import os
from pathlib import Path

from dotenv import load_dotenv

_BACKEND_DIR = Path(__file__).resolve().parent
load_dotenv(_BACKEND_DIR / ".env")


class Settings:
    CLERK_PUBLISHABLE_KEY: str = os.getenv("CLERK_PUBLISHABLE_KEY", "")
    DB_PATH: Path = Path(os.getenv("DB_PATH", str(_BACKEND_DIR / "data.db")))
    # All scheduling and session-day logic uses this timezone (never system local time).
    DEFAULT_TZ: str = "Asia/Kolkata"
    DEFAULT_SCAN_TIME: str = "09:00"


settings = Settings()

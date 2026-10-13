"""Lightweight settings loaded from backend/.env (or the process environment)."""
import os
from pathlib import Path
from typing import Callable

from dotenv import load_dotenv

_BACKEND_DIR = Path(__file__).resolve().parent
_ENV_PATH = _BACKEND_DIR / ".env"
load_dotenv(_ENV_PATH)


def get_or_create_secret(name: str, factory: Callable[[], str], env_path: Path = _ENV_PATH) -> str:
    """Return a persisted secret, generating and storing it in `.env` on first use."""
    value = os.environ.get(name, "").strip()
    if value:
        return value
    if env_path.is_file():
        for line in env_path.read_text().splitlines():
            k, _, v = line.partition("=")
            if k.strip() == name and v.strip():
                return v.strip().strip('"').strip("'")
    value = factory()
    fd = os.open(env_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a") as f:
        f.write(f"{name}={value}\n")
    return value


class Settings:
    CLERK_PUBLISHABLE_KEY: str = os.getenv("CLERK_PUBLISHABLE_KEY", "")
    DB_PATH: Path = Path(os.getenv("DB_PATH", str(_BACKEND_DIR / "data.db")))
    # All scheduling and session-day logic uses this timezone (never system local time).
    DEFAULT_TZ: str = "Asia/Kolkata"
    DEFAULT_SCAN_TIME: str = "09:00"


settings = Settings()

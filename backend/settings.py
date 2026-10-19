import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = REPO_ROOT / "data" / "goldryn.db"
DEFAULT_LOG_DIR = REPO_ROOT / "logs"

_FALSY = {"0", "false", "no", "off"}


@dataclass(frozen=True)
class Settings:
    """Everything the app reads from the environment, resolved once at startup."""

    username: str
    password_hash: bytes
    db_path: Path
    cookie_secure: bool
    # No default on purpose: anything building Settings by hand (the tests) must
    # choose where logs go, so it can't write into the repo's logs/ by accident.
    log_dir: Path


def load_settings() -> Settings:
    """
    Read settings from the environment.

    GOLDRYN_USERNAME / GOLDRYN_PASSWORD_HASH are required: Windows always sets
    USERNAME to the OS login, so the names are prefixed to avoid picking it up.
    """
    username = os.getenv("GOLDRYN_USERNAME")
    password_hash = os.getenv("GOLDRYN_PASSWORD_HASH")
    missing = [
        name
        for name, value in (("GOLDRYN_USERNAME", username), ("GOLDRYN_PASSWORD_HASH", password_hash))
        if not value
    ]
    if missing:
        raise RuntimeError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            "Copy .env.example to .env and fill it in (see backend/hash_password.py)."
        )

    db_path = os.getenv("GOLDRYN_DB_PATH")
    cookie_secure = os.getenv("GOLDRYN_COOKIE_SECURE", "true").strip().lower() not in _FALSY
    log_dir = os.getenv("GOLDRYN_LOG_DIR")

    return Settings(
        username=username,
        password_hash=password_hash.encode(),
        db_path=Path(db_path) if db_path else DEFAULT_DB_PATH,
        cookie_secure=cookie_secure,
        log_dir=Path(log_dir) if log_dir else DEFAULT_LOG_DIR,
    )

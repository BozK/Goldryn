import secrets
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Annotated

import bcrypt
from fastapi import Cookie, HTTPException, Request, status

from settings import Settings

SESSION_COOKIE = "session_id"
SESSION_TTL = timedelta(days=7)

# bcrypt only looks at the first 72 bytes, and bcrypt>=5 raises instead of truncating.
BCRYPT_MAX_BYTES = 72


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SessionStore:
    """
    In-memory sessions: {session_id: (username, expires_at)}.

    Lives in process memory, so a restart logs everyone out and the server must
    run as a single worker. Expiry is enforced here as well as by the cookie's
    max_age, so a copied cookie stops working after SESSION_TTL regardless.
    """

    def __init__(self, ttl: timedelta = SESSION_TTL, clock: Callable[[], datetime] = _utcnow):
        self._ttl = ttl
        self._clock = clock
        self._sessions: dict[str, tuple[str, datetime]] = {}

    def create(self, username: str) -> str:
        session_id = secrets.token_urlsafe(32)
        self._sessions[session_id] = (username, self._clock() + self._ttl)
        return session_id

    def get(self, session_id: str) -> str | None:
        """Return the session's username, or None if it is unknown or expired."""
        entry = self._sessions.get(session_id)
        if entry is None:
            return None
        username, expires_at = entry
        if self._clock() >= expires_at:
            del self._sessions[session_id]
            return None
        return username

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)


def check_credentials(settings: Settings, username: str, password: str) -> bool:
    """
    Check a login attempt against the configured user.

    Both checks always run, so a wrong username costs the same bcrypt time as a
    wrong password and doesn't reveal which one was wrong.
    """
    username_ok = secrets.compare_digest(username.encode(), settings.username.encode())
    password_bytes = password.encode()
    if len(password_bytes) > BCRYPT_MAX_BYTES:
        return False
    password_ok = bcrypt.checkpw(password_bytes, settings.password_hash)
    return username_ok and password_ok


def get_current_user(
    request: Request,
    session_id: Annotated[str | None, Cookie()] = None,
) -> str:
    """Dependency for every protected route: the logged-in username, or 401."""
    username = request.app.state.sessions.get(session_id) if session_id else None
    if username is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not logged in")
    return username

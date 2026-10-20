import math
import secrets
import threading
from collections import deque
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Annotated

import bcrypt
from fastapi import Cookie, HTTPException, Request, status

from settings import Settings

SESSION_COOKIE = "session_id"
SESSION_TTL = timedelta(days=7)

# Login attempts allowed per client IP within LOGIN_WINDOW. A successful login resets the count.
LOGIN_MAX_ATTEMPTS = 5
LOGIN_WINDOW = timedelta(minutes=15)

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


class LoginLimiter:
    """
    In-memory login throttle: {client_key: deque of attempt times}, oldest first.

    Every attempt counts when it starts, not when it fails, so a burst of
    parallel requests can't all slip past the check while bcrypt runs. A
    successful login then clears the key. Like SessionStore, it lives in
    process memory: a restart clears it, and it relies on a single worker.

    There's deliberately no global (per-account) limit: anyone could trip it and
    lock the real user out.
    """

    def __init__(
        self,
        max_attempts: int = LOGIN_MAX_ATTEMPTS,
        window: timedelta = LOGIN_WINDOW,
        clock: Callable[[], datetime] = _utcnow,
    ):
        self._max_attempts = max_attempts
        self._window = window
        self._clock = clock
        self._attempts: dict[str, deque[datetime]] = {}
        # The login route is sync, so attempts arrive on threadpool workers.
        self._lock = threading.Lock()

    def attempt(self, key: str) -> int | None:
        """
        Count an attempt for key and return None, or, if key is out of attempts,
        count nothing and return the whole seconds until its oldest one expires.
        """
        with self._lock:
            now = self._clock()
            self._prune(now)
            times = self._attempts.setdefault(key, deque())
            if len(times) >= self._max_attempts:
                wait = (times[0] + self._window - now).total_seconds()
                return max(1, math.ceil(wait))
            times.append(now)
            return None

    def reset(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)

    def _prune(self, now: datetime) -> None:
        """Drop expired attempts, and keys left with none, so the dict doesn't grow without bound."""
        cutoff = now - self._window
        for key in list(self._attempts):
            times = self._attempts[key]
            while times and times[0] <= cutoff:
                times.popleft()
            if not times:
                del self._attempts[key]


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

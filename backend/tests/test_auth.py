from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from auth import LOGIN_MAX_ATTEMPTS, SESSION_COOKIE, LoginLimiter, SessionStore
from GoldrynBackend import create_app
from settings import DEFAULT_DB_PATH, load_settings

from conftest import PASSWORD, USERNAME


def login(client, username=USERNAME, password=PASSWORD, ip=None):
    headers = {"CF-Connecting-IP": ip} if ip else None
    return client.post("/api/auth/login", json={"username": username, "password": password}, headers=headers)


# ============================================================================
# Login
# ============================================================================


def test_login_sets_session_cookie(anon):
    res = login(anon)
    assert res.status_code == 200
    assert res.json() == {"username": USERNAME}

    cookie = res.headers["set-cookie"]
    assert cookie.startswith(f"{SESSION_COOKIE}=")
    assert "HttpOnly" in cookie
    assert "Max-Age=604800" in cookie
    assert "samesite=lax" in cookie.lower()


@pytest.mark.parametrize(
    "username, password",
    [
        ("nobody", PASSWORD),
        (USERNAME, "wrong password"),
        (USERNAME, ""),
        ("", ""),
        (USERNAME, "x" * 100),  # over bcrypt's 72-byte limit: rejected, not a 500
        ("téster", PASSWORD),  # non-ASCII usernames compare without raising
    ],
)
def test_bad_credentials_are_400(anon, username, password):
    res = login(anon, username, password)
    assert res.status_code == 400
    assert SESSION_COOKIE not in res.cookies


def test_login_missing_fields_is_422(anon):
    assert anon.post("/api/auth/login", json={"username": USERNAME}).status_code == 422


def test_cookie_is_secure_when_configured(settings):
    secure_app = create_app(replace(settings, cookie_secure=True))
    res = login(TestClient(secure_app))
    assert "Secure" in res.headers["set-cookie"]


# ============================================================================
# Login rate limit
# ============================================================================


def test_too_many_attempts_is_429_with_retry_after(anon):
    for _ in range(LOGIN_MAX_ATTEMPTS):
        assert login(anon, password="wrong", ip="203.0.113.7").status_code == 400

    res = login(anon, password="wrong", ip="203.0.113.7")
    assert res.status_code == 429
    assert 0 < int(res.headers["retry-after"]) <= 15 * 60


def test_blocked_ip_cannot_log_in_even_with_the_right_password(anon):
    for _ in range(LOGIN_MAX_ATTEMPTS):
        login(anon, password="wrong", ip="203.0.113.7")
    res = login(anon, ip="203.0.113.7")
    assert res.status_code == 429
    assert SESSION_COOKIE not in res.cookies


def test_rate_limit_is_per_ip(anon):
    for _ in range(LOGIN_MAX_ATTEMPTS):
        login(anon, password="wrong", ip="203.0.113.7")
    assert login(anon, ip="198.51.100.2").status_code == 200


def test_successful_login_resets_the_count(anon):
    for _ in range(LOGIN_MAX_ATTEMPTS - 1):
        login(anon, password="wrong", ip="203.0.113.7")
    assert login(anon, ip="203.0.113.7").status_code == 200

    for _ in range(LOGIN_MAX_ATTEMPTS - 1):
        assert login(anon, password="wrong", ip="203.0.113.7").status_code == 400


def test_requests_without_ip_header_share_a_bucket(anon):
    for _ in range(LOGIN_MAX_ATTEMPTS):
        login(anon, password="wrong")
    assert login(anon, password="wrong").status_code == 429


def test_invalid_body_does_not_use_an_attempt(anon):
    for _ in range(LOGIN_MAX_ATTEMPTS + 1):
        assert anon.post("/api/auth/login", json={"username": USERNAME}).status_code == 422
    assert login(anon).status_code == 200


# ============================================================================
# Session checks
# ============================================================================


def test_me_requires_session(anon):
    assert anon.get("/api/me").status_code == 401


def test_me_rejects_unknown_session(anon):
    anon.cookies.set(SESSION_COOKIE, "made-up")
    assert anon.get("/api/me").status_code == 401


def test_me_returns_username(client):
    res = client.get("/api/me")
    assert res.status_code == 200
    assert res.json() == {"username": USERNAME}


def test_sessions_do_not_survive_a_new_app(client, settings):
    """A restart (fresh app, same DB) logs everyone out."""
    restarted = TestClient(create_app(settings))
    restarted.cookies = client.cookies
    assert restarted.get("/api/me").status_code == 401


# ============================================================================
# Logout
# ============================================================================


def test_logout_ends_session(client):
    res = client.post("/api/auth/logout")
    assert res.status_code == 200
    assert client.get("/api/me").status_code == 401


def test_logout_only_ends_callers_session(app):
    laptop, phone = TestClient(app), TestClient(app)
    login(laptop).raise_for_status()
    login(phone).raise_for_status()

    laptop.post("/api/auth/logout").raise_for_status()

    assert laptop.get("/api/me").status_code == 401
    assert phone.get("/api/me").status_code == 200


def test_logout_without_session_is_ok(anon):
    assert anon.post("/api/auth/logout").status_code == 200


def test_old_cookie_is_dead_after_logout(app):
    c = TestClient(app)
    login(c).raise_for_status()
    stolen = c.cookies.get(SESSION_COOKIE)
    c.post("/api/auth/logout").raise_for_status()

    other = TestClient(app)
    other.cookies.set(SESSION_COOKIE, stolen)
    assert other.get("/api/me").status_code == 401


# ============================================================================
# SessionStore
# ============================================================================


class FakeClock:
    def __init__(self):
        self.now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def __call__(self):
        return self.now


def test_session_expires_server_side():
    clock = FakeClock()
    store = SessionStore(ttl=timedelta(days=7), clock=clock)
    sid = store.create(USERNAME)

    clock.now += timedelta(days=7) - timedelta(seconds=1)
    assert store.get(sid) == USERNAME

    clock.now += timedelta(seconds=1)
    assert store.get(sid) is None


def test_session_ids_are_unique_and_unguessable():
    store = SessionStore()
    ids = {store.create(USERNAME) for _ in range(100)}
    assert len(ids) == 100
    assert all(len(sid) >= 40 for sid in ids)


# ============================================================================
# LoginLimiter
# ============================================================================


def test_limiter_allows_max_attempts_then_blocks():
    limiter = LoginLimiter(max_attempts=3, window=timedelta(minutes=15), clock=FakeClock())
    assert [limiter.attempt("a") for _ in range(3)] == [None, None, None]
    assert limiter.attempt("a") == 15 * 60


def test_limiter_retry_after_counts_down_to_oldest_attempt_expiring():
    clock = FakeClock()
    limiter = LoginLimiter(max_attempts=2, window=timedelta(minutes=15), clock=clock)
    limiter.attempt("a")
    clock.now += timedelta(minutes=5)
    limiter.attempt("a")

    clock.now += timedelta(minutes=9, seconds=30)
    assert limiter.attempt("a") == 30

    # The oldest attempt has expired, so one more is allowed, and then the second one gates.
    clock.now += timedelta(seconds=30)
    assert limiter.attempt("a") is None
    assert limiter.attempt("a") == 5 * 60


def test_limiter_blocked_attempts_do_not_extend_the_block():
    clock = FakeClock()
    limiter = LoginLimiter(max_attempts=1, window=timedelta(minutes=15), clock=clock)
    limiter.attempt("a")
    for _ in range(10):
        clock.now += timedelta(minutes=1)
        limiter.attempt("a")
    clock.now += timedelta(minutes=5)
    assert limiter.attempt("a") is None


def test_limiter_reset_clears_a_key():
    limiter = LoginLimiter(max_attempts=1, clock=FakeClock())
    limiter.attempt("a")
    limiter.reset("a")
    assert limiter.attempt("a") is None


def test_limiter_forgets_expired_keys():
    clock = FakeClock()
    limiter = LoginLimiter(max_attempts=1, window=timedelta(minutes=15), clock=clock)
    for ip in ("a", "b", "c"):
        limiter.attempt(ip)
    clock.now += timedelta(minutes=15)
    limiter.attempt("d")
    assert set(limiter._attempts) == {"d"}


# ============================================================================
# Settings
# ============================================================================


def test_load_settings_requires_credentials(monkeypatch):
    monkeypatch.delenv("GOLDRYN_USERNAME", raising=False)
    monkeypatch.delenv("GOLDRYN_PASSWORD_HASH", raising=False)
    # Windows' own USERNAME must not stand in for GOLDRYN_USERNAME.
    monkeypatch.setenv("USERNAME", "someone")
    with pytest.raises(RuntimeError, match="GOLDRYN_USERNAME, GOLDRYN_PASSWORD_HASH"):
        load_settings()


@pytest.mark.parametrize(
    "raw, expected",
    [(None, True), ("true", True), ("1", True), ("false", False), ("0", False), (" No ", False)],
)
def test_load_settings_cookie_secure(monkeypatch, raw, expected):
    monkeypatch.setenv("GOLDRYN_USERNAME", USERNAME)
    monkeypatch.setenv("GOLDRYN_PASSWORD_HASH", "$2b$04$hash")
    if raw is None:
        monkeypatch.delenv("GOLDRYN_COOKIE_SECURE", raising=False)
    else:
        monkeypatch.setenv("GOLDRYN_COOKIE_SECURE", raw)

    settings = load_settings()
    assert settings.cookie_secure is expected
    assert settings.db_path == DEFAULT_DB_PATH
    assert settings.password_hash == b"$2b$04$hash"

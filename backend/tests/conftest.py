import bcrypt
import pytest
from fastapi.testclient import TestClient

from GoldrynBackend import create_app
from settings import Settings

USERNAME = "tester"
PASSWORD = "correct horse battery staple"
# Minimum cost: these tests exercise the login flow, not bcrypt.
PASSWORD_HASH = bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt(rounds=4))


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        username=USERNAME,
        password_hash=PASSWORD_HASH,
        db_path=tmp_path / "goldryn.db",
        # TestClient talks plain http, and httpx won't send a Secure cookie over it.
        cookie_secure=False,
        log_dir=tmp_path / "logs",
    )


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def anon(app) -> TestClient:
    """A client with no session."""
    return TestClient(app)


@pytest.fixture
def client(app) -> TestClient:
    """A logged-in client."""
    c = TestClient(app)
    c.post("/api/auth/login", json={"username": USERNAME, "password": PASSWORD}).raise_for_status()
    return c

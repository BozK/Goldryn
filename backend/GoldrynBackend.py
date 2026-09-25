from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.staticfiles import StaticFiles

from auth import SESSION_COOKIE, SESSION_TTL, SessionStore, check_credentials, get_current_user
from db import init_db
from GoldrynModels import LoginRequest, Me, MessageResponse
from settings import REPO_ROOT, Settings, load_settings

FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"

CurrentUser = Annotated[str, Depends(get_current_user)]

# ============================================================================
# Auth routes
# ============================================================================

auth_router = APIRouter(prefix="/api")


@auth_router.post("/auth/login", response_model=Me)
def login(credentials: LoginRequest, request: Request, response: Response):
    settings: Settings = request.app.state.settings
    if not check_credentials(settings, credentials.username, credentials.password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid username or password")

    session_id = request.app.state.sessions.create(settings.username)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=session_id,
        max_age=int(SESSION_TTL.total_seconds()),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    return Me(username=settings.username)


@auth_router.post("/auth/logout", response_model=MessageResponse)
def logout(
    request: Request,
    response: Response,
    session_id: Annotated[str | None, Cookie()] = None,
):
    """Ends the caller's own session (other browsers stay logged in). Safe to call when logged out."""
    if session_id:
        request.app.state.sessions.delete(session_id)
    response.delete_cookie(
        key=SESSION_COOKIE,
        httponly=True,
        secure=request.app.state.settings.cookie_secure,
        samesite="lax",
    )
    return MessageResponse(message="Logged out")


@auth_router.get("/me", response_model=Me)
def me(username: CurrentUser):
    return Me(username=username)


# ============================================================================
# App factory
# ============================================================================


def create_app(settings: Settings | None = None) -> FastAPI:
    """
    Build the app. Everything is wired here rather than under __main__, so tests
    and `uvicorn --factory` get exactly the same app as `python GoldrynBackend.py`.
    """
    settings = settings or load_settings()
    init_db(settings.db_path)

    app = FastAPI(title="Goldryn API", version="1.0.0")
    app.state.settings = settings
    app.state.sessions = SessionStore()

    app.include_router(auth_router)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    # Mounted last: "/" would otherwise shadow every route registered after it.
    if FRONTEND_DIST.is_dir():
        app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")

    return app


if __name__ == "__main__":
    import uvicorn
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
    # One worker only: sessions live in this process's memory.
    uvicorn.run(create_app(), host="127.0.0.1", port=8000)

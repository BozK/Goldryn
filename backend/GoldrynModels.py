"""Request/response models. Shapes mirror frontend/src/lib/GoldrynModels.tsx."""

from pydantic import BaseModel

# ============================================================================
# Auth
# ============================================================================


class LoginRequest(BaseModel):
    username: str
    password: str


class Me(BaseModel):
    username: str


# ============================================================================
# Generic
# ============================================================================


class MessageResponse(BaseModel):
    message: str

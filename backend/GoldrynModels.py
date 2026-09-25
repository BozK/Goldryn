"""
Request/response models. Shapes mirror frontend/src/lib/GoldrynModels.tsx.

PATCH models declare required-in-the-DB fields (name, body, date) as non-optional
types with a None default: omitting them is fine, but an explicit null fails
validation, because a default is never validated while a sent value always is.
Nullable columns are `X | None = None`, so null clears them.
"""

import re
from datetime import date
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints

# ============================================================================
# Field types
# ============================================================================

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
# The frontend owns the palette (and falls back for unknown values), so any short string is allowed.
Color = Annotated[str, StringConstraints(max_length=32)]
# Capped at 100 years: beyond that, "next due" would overflow date arithmetic and SQLite integers.
CadenceDays = Annotated[int, Field(ge=1, le=36500)]
Body = Annotated[str, StringConstraints(min_length=1, pattern=r"\S")]
Cost = Annotated[float, Field(ge=0, allow_inf_nan=False)]

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _require_iso_date_string(value: object) -> object:
    # Pydantic's lax date parsing also takes Unix timestamps and other formats;
    # the API contract is "YYYY-MM-DD" only.
    if not isinstance(value, str) or not _ISO_DATE.match(value):
        raise ValueError("must be a date in YYYY-MM-DD format")
    return value


IsoDate = Annotated[date, BeforeValidator(_require_iso_date_string)]


class RequestModel(BaseModel):
    """Rejects unknown fields, so a typo'd field name is a 422 rather than silently ignored."""

    model_config = ConfigDict(extra="forbid")


# ============================================================================
# Auth
# ============================================================================


class LoginRequest(BaseModel):
    username: str
    password: str


class Me(BaseModel):
    username: str


# ============================================================================
# Items
# ============================================================================


class ItemCreate(RequestModel):
    name: Name
    color: Color | None = None
    cadence_days: CadenceDays | None = None
    next_maintenance_notes: str | None = None


class ItemPatch(RequestModel):
    name: Name = None  # omit to keep; null is rejected
    color: Color | None = None
    cadence_days: CadenceDays | None = None
    next_maintenance_notes: str | None = None


class ItemSummary(BaseModel):
    """One row of GET /api/items."""

    id: int
    name: str
    color: str | None
    cadence_days: int | None
    next_due: date | None


class Item(BaseModel):
    """Item header fields, returned by POST/PATCH /api/items."""

    id: int
    name: str
    color: str | None
    cadence_days: int | None
    next_maintenance_notes: str | None
    created_at: str
    next_due: date | None


# ============================================================================
# Notes
# ============================================================================


class NoteCreate(RequestModel):
    body: Body


class NotePatch(RequestModel):
    body: Body = None  # omit to keep; null is rejected


class Note(BaseModel):
    id: int
    body: str
    created_at: str


# ============================================================================
# Maintenance Records
# ============================================================================


class MaintenanceRecordCreate(RequestModel):
    date: IsoDate
    summary: str | None = None
    cost: Cost | None = None
    contractor_info: str | None = None


class MaintenanceRecordPatch(RequestModel):
    date: IsoDate = None  # omit to keep; null is rejected
    summary: str | None = None
    cost: Cost | None = None
    contractor_info: str | None = None


class MaintenanceRecord(BaseModel):
    id: int
    date: date
    summary: str | None
    cost: float | None
    contractor_info: str | None


# ============================================================================
# Item detail
# ============================================================================


class ItemDetail(Item):
    """GET /api/items/{id}: the item plus all of its children."""

    notes: list[Note]
    maintenance_records: list[MaintenanceRecord]


# ============================================================================
# Generic
# ============================================================================


class MessageResponse(BaseModel):
    message: str

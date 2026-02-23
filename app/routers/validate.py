from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

router = APIRouter()

# Data element UIDs for the address fields we validate
DE_TOWNSHIP = "QcFEXzah0f1"   # Permanent Address - Township (MBDR)
DE_LOCATION = "hQnTVzOd0m9"   # Permanent Address - Ward/Village Location (Urban/Rural)
DE_WARD     = "ZT3zBscjD24"   # Permanent Address - Ward Name
DE_VILLAGE  = "C5ppG8eJSKs"   # Permanent Address - Village Name

# Data element UIDs for ICD10 cause-of-death fields (Death Register program)
DE_ICD10_FIELDS = {
    "TJlsMB053WZ": "CoD - Cause of Death I A",
    "Wntbkbl2ext": "CoD - Cause of Death I B",
    "auAvndfLb5x": "CoD - Cause of Death I C",
    "nQy5xQrOMXj": "CoD - Underlying Cause of Death",
}


# ── Incoming payload schema ─────────────────────────────────────────────────

class DataValue(BaseModel):
    dataElement: str
    value: str


class Event(BaseModel):
    event: str
    dataValues: list[DataValue]


class EventPayload(BaseModel):
    events: list[Event]


# ── Response schema ─────────────────────────────────────────────────────────

class ValidationError(BaseModel):
    event: str
    field: str
    message: str


class ValidationResult(BaseModel):
    valid: bool
    errors: list[ValidationError] = []


# ── Helper ───────────────────────────────────────────────────────────────────

def extract(data_values: list[DataValue], uid: str) -> str | None:
    for dv in data_values:
        if dv.dataElement == uid:
            return dv.value.strip() or None
    return None


# ── Endpoint ─────────────────────────────────────────────────────────────────

@router.post("/validate", response_model=ValidationResult)
async def validate_events(
    payload: EventPayload,
    db: AsyncSession = Depends(get_db),
) -> ValidationResult:
    from app.validation import validate_event

    errors = []
    for event in payload.events:
        errors.extend(await validate_event(db, event.event, event.dataValues))

    return ValidationResult(valid=not errors, errors=errors)

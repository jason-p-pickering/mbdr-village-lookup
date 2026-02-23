"""
Core validation logic shared between /validate and /proxy/tracker.
"""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.routers.validate import (
    DE_TOWNSHIP,
    DE_LOCATION,
    DE_WARD,
    DE_VILLAGE,
    DE_ICD10_FIELDS,
    ValidationError,
    extract,
)


async def check_ward(db: AsyncSession, township_code: str, ward_code: str) -> bool:
    row = await db.execute(
        text(
            """
            SELECT 1
            FROM   wards w
            JOIN   townships t ON t.id = w.township_id
            WHERE  t.code = :township_code
              AND  w.code = :ward_code
            LIMIT 1
            """
        ),
        {"township_code": township_code, "ward_code": ward_code},
    )
    return row.first() is not None


async def check_icd10_code(db: AsyncSession, code: str) -> bool:
    row = await db.execute(
        text("SELECT 1 FROM icd10_codes WHERE code = :code LIMIT 1"),
        {"code": code},
    )
    return row.first() is not None


async def check_village(db: AsyncSession, township_code: str, village_code: str) -> bool:
    row = await db.execute(
        text(
            """
            SELECT 1
            FROM   villages v
            JOIN   townships t ON t.id = v.township_id
            WHERE  t.code = :township_code
              AND  v.code = :village_code
            LIMIT 1
            """
        ),
        {"township_code": township_code, "village_code": village_code},
    )
    return row.first() is not None


async def validate_event(db: AsyncSession, event_uid: str, data_values: list) -> list[ValidationError]:
    """
    Validate a single event's data values.
    Checks address hierarchy consistency and ICD10 code validity.
    Returns a list of ValidationError (empty = valid).
    """
    errors: list[ValidationError] = []

    # ── Address validation ───────────────────────────────────────────────────
    township_code = extract(data_values, DE_TOWNSHIP)
    location      = extract(data_values, DE_LOCATION)
    ward_code     = extract(data_values, DE_WARD)
    village_code  = extract(data_values, DE_VILLAGE)

    if township_code and location:
        if location == "Urban":
            if ward_code and not await check_ward(db, township_code, ward_code):
                errors.append(ValidationError(
                    event=event_uid,
                    field=DE_WARD,
                    message=f"Ward '{ward_code}' does not belong to township '{township_code}'.",
                ))
        elif location == "Rural":
            if village_code and not await check_village(db, township_code, village_code):
                errors.append(ValidationError(
                    event=event_uid,
                    field=DE_VILLAGE,
                    message=f"Village '{village_code}' does not belong to township '{township_code}'.",
                ))

    # ── ICD10 validation ─────────────────────────────────────────────────────
    for de_uid, de_name in DE_ICD10_FIELDS.items():
        value = extract(data_values, de_uid)
        if value and not await check_icd10_code(db, value):
            errors.append(ValidationError(
                event=event_uid,
                field=de_uid,
                message=f"'{value}' is not a valid ICD10 code ({de_name}).",
            ))

    return errors

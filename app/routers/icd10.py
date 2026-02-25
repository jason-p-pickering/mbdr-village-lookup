import re

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import ICD10Out, ICD10Page

router = APIRouter()

# Matches ICD10 code patterns: letter(s) optionally followed by digits/dots
# e.g. "A", "A0", "A00", "A00.", "A00.0"  →  sort by clinical code order
_CODE_PATTERN = re.compile(r"^[A-Za-z]\d*\.?\d*$")


@router.get("/icd10", response_model=ICD10Page)
async def search_icd10(
    q: str | None = Query(None, min_length=3, max_length=100, description="Search term (code or description)"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> ICD10Page:
    offset = (page - 1) * limit

    if q:
        count_row = await db.execute(
            text("SELECT COUNT(*) FROM icd10_codes WHERE name ILIKE '%' || :q || '%'"),
            {"q": q},
        )
        total = count_row.scalar() or 0

        order = "icd_code" if _CODE_PATTERN.match(q) else "similarity(name, :q) DESC, icd_code"

        rows = await db.execute(
            text(
                f"""
                SELECT uid, code, icd_code, name
                FROM   icd10_codes
                WHERE  name ILIKE '%' || :q || '%'
                ORDER  BY {order}
                LIMIT  :limit OFFSET :offset
                """
            ),
            {"q": q, "limit": limit, "offset": offset},
        )
    else:
        count_row = await db.execute(text("SELECT COUNT(*) FROM icd10_codes"))
        total = count_row.scalar() or 0

        rows = await db.execute(
            text(
                """
                SELECT uid, code, icd_code, name
                FROM   icd10_codes
                ORDER  BY icd_code, name
                LIMIT  :limit OFFSET :offset
                """
            ),
            {"limit": limit, "offset": offset},
        )

    results = [
        ICD10Out(uid=r.uid, code=r.code, icd_code=r.icd_code, name=r.name)
        for r in rows.mappings()
    ]
    return ICD10Page(page=page, limit=limit, total=total, results=results)

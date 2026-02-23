from fastapi import APIRouter, Depends, Query, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import TownshipOut, WardOut, VillageOut

router = APIRouter()


@router.get("/townships", response_model=list[TownshipOut])
async def list_townships(request: Request):
    return request.app.state.townships_cache


@router.get("/wards", response_model=list[WardOut])
async def search_wards(
    township_uid: str = Query(..., description="DHIS2 UID of the township"),
    q: str | None = Query(None, description="Ward name search string"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[WardOut]:
    if q:
        stmt = text(
            """
            SELECT w.uid, w.code, w.name, w.name_my
            FROM   wards w
            JOIN   townships t ON t.id = w.township_id
            WHERE  t.uid = :township_uid
              AND  w.name ILIKE '%' || :q || '%'
            ORDER  BY similarity(w.name, :q) DESC
            LIMIT  :limit
            """
        )
        rows = await db.execute(stmt, {"township_uid": township_uid, "q": q, "limit": limit})
    else:
        stmt = text(
            """
            SELECT w.uid, w.code, w.name, w.name_my
            FROM   wards w
            JOIN   townships t ON t.id = w.township_id
            WHERE  t.uid = :township_uid
            ORDER  BY w.name
            LIMIT  :limit
            """
        )
        rows = await db.execute(stmt, {"township_uid": township_uid, "limit": limit})

    return [WardOut(uid=r.uid, code=r.code, name=r.name, name_my=r.name_my) for r in rows.mappings()]


@router.get("/villages", response_model=list[VillageOut])
async def search_villages(
    township_uid: str = Query(..., description="DHIS2 UID of the township"),
    q: str | None = Query(None, description="Village name search string"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[VillageOut]:
    if q:
        stmt = text(
            """
            SELECT v.uid, v.code, v.name, v.name_my
            FROM   villages v
            JOIN   townships t ON t.id = v.township_id
            WHERE  t.uid = :township_uid
              AND  v.name ILIKE '%' || :q || '%'
            ORDER  BY similarity(v.name, :q) DESC
            LIMIT  :limit
            """
        )
        rows = await db.execute(stmt, {"township_uid": township_uid, "q": q, "limit": limit})
    else:
        stmt = text(
            """
            SELECT v.uid, v.code, v.name, v.name_my
            FROM   villages v
            JOIN   townships t ON t.id = v.township_id
            WHERE  t.uid = :township_uid
            ORDER  BY v.name
            LIMIT  :limit
            """
        )
        rows = await db.execute(stmt, {"township_uid": township_uid, "limit": limit})

    return [VillageOut(uid=r.uid, code=r.code, name=r.name, name_my=r.name_my) for r in rows.mappings()]

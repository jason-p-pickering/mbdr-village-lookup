from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import Township
from app.routers.icd10 import router as icd10_router
from app.routers.proxy import router as proxy_router
from app.routers.validate import router as validate_router
from app.routers.villages import router as villages_router
from app.schemas import TownshipOut


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load townships into memory
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Township).order_by(Township.name))
        townships = result.scalars().all()
        app.state.townships_cache = [TownshipOut.model_validate(t) for t in townships]

    # Shared async HTTP client for proxying to DHIS2
    async with httpx.AsyncClient(timeout=60) as client:
        app.state.http_client = client
        yield

    app.state.townships_cache = []


app = FastAPI(title="Village Lookup", lifespan=lifespan)


_CACHED_PATHS = {"/townships", "/wards", "/villages"}


@app.middleware("http")
async def add_cache_headers(request: Request, call_next):
    response = await call_next(request)
    if request.url.path in _CACHED_PATHS:
        response.headers["Cache-Control"] = "private, max-age=3600"
    return response


@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(villages_router)
app.include_router(icd10_router)
app.include_router(validate_router)
app.include_router(proxy_router)

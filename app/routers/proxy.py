import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.routers.validate import DataValue, ValidationError
from app.validation import validate_event

router = APIRouter()

TARGET_PROGRAM = "cUjoGJK4gPL"
DHIS2_TRACKER_URL = f"{settings.DHIS2_BASE_URL}/api/tracker"
VALIDATION_ERROR_CODE = "E1301"  # custom code: address hierarchy mismatch


async def relay(request: Request, body: bytes, params: dict) -> Response:
    """Forward the request to DHIS2, preserving the session cookie and returning
    the response unchanged."""
    client = request.app.state.http_client
    cookie = request.headers.get("cookie", "")

    dhis2_resp = await client.post(
        DHIS2_TRACKER_URL,
        content=body,
        params=params,
        headers={
            "Content-Type": "application/json",
            "Cookie": cookie,
        },
    )

    return Response(
        content=dhis2_resp.content,
        status_code=dhis2_resp.status_code,
        media_type=dhis2_resp.headers.get("content-type", "application/json"),
    )


@router.post("/proxy/tracker")
async def proxy_tracker(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    body = await request.body()
    params = dict(request.query_params)

    # Only validate synchronous submissions — relay everything else straight through
    if params.get("async") != "false":
        return await relay(request, body, params)

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return await relay(request, body, params)

    events = payload.get("events", [])

    # Only validate events for the target program — relay the rest unchanged
    target_events = [e for e in events if e.get("program") == TARGET_PROGRAM]
    if not target_events:
        return await relay(request, body, params)

    # Validate
    errors: list[ValidationError] = []
    for event in target_events:
        dvs = [DataValue(dataElement=dv["dataElement"], value=dv["value"])
               for dv in event.get("dataValues", [])]
        errors.extend(await validate_event(db, event.get("event", ""), dvs))

    if errors:
        total = len(events)
        body = {
            "status": "ERROR",
            "validationReport": {
                "errorReports": [
                    {
                        "message": e.message,
                        "errorCode": VALIDATION_ERROR_CODE,
                        "trackerType": "EVENT",
                        "uid": e.event,
                    }
                    for e in errors
                ],
                "warningReports": [],
            },
            "stats": {
                "created": 0,
                "updated": 0,
                "deleted": 0,
                "ignored": total,
                "total": total,
            },
        }
        return Response(
            content=json.dumps(body),
            status_code=409,
            media_type="application/json",
        )

    return await relay(request, body, params)

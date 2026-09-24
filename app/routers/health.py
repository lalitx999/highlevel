import time
from datetime import datetime, timezone
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from app.core.database import check_database_health
from app.schemas.common import HealthCheckResponse

router = APIRouter(tags=["Health"])

START_TIME = time.time()


@router.get(
    "/health",
    response_model=HealthCheckResponse,
    summary="Service Health Check",
)
async def get_health():
    """Returns application health status and database connectivity check."""
    db_connected = await check_database_health()
    uptime_seconds = int(time.time() - START_TIME)

    health_status = "UP" if db_connected else "DEGRADED"
    status_code = status.HTTP_200_OK if db_connected else status.HTTP_503_SERVICE_UNAVAILABLE

    response_data = HealthCheckResponse(
        status=health_status,
        timestamp=datetime.now(timezone.utc).isoformat(),
        uptime_seconds=uptime_seconds,
        checks={
            "database": "CONNECTED" if db_connected else "DISCONNECTED",
        },
        version="1.0.0",
    )

    return JSONResponse(status_code=status_code, content=response_data.model_dump())

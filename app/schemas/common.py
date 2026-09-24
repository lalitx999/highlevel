from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class HealthCheckResponse(BaseModel):
    status: str
    timestamp: str
    uptime_seconds: int
    checks: Dict[str, str]
    version: str = "1.0.0"


class StandardResponse(BaseModel):
    status: str
    message: Optional[str] = None
    data: Optional[Any] = None


class OutboundWebhookResult(BaseModel):
    status: str
    deliveryMethod: Optional[str] = None
    lineUserId: Optional[str] = None
    latency_ms: Optional[int] = None
    reason: Optional[str] = None

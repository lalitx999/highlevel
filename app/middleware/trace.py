import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from app.core.logging import set_trace_id


class TracingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        # Extract existing X-Trace-Id header or generate a new UUID v4
        incoming_trace_id = request.headers.get("x-trace-id") or request.headers.get("traceparent")
        trace_id = set_trace_id(incoming_trace_id or str(uuid.uuid4()))

        response = await call_next(request)
        response.headers["X-Trace-Id"] = trace_id
        return response

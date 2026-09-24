from contextlib import asynccontextmanager
import uvicorn
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.config import settings
from app.core.database import check_database_health, engine
from app.core.logging import get_trace_id, logger
from app.middleware.trace import TracingMiddleware
from app.routers import health_router, oauth_router, webhooks_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    logger.info(
        "Starting LINE OA <-> GoHighLevel Middleware",
        environment=settings.NODE_ENV,
        port=settings.PORT,
    )
    db_ok = await check_database_health()
    if db_ok:
        logger.info("Database connection initialized and healthy")
    else:
        logger.warn(
            "Initial database connection check failed. Will retry on subsequent requests.",
            error_code="DB_STARTUP_WARN",
        )

    yield

    # --- Shutdown ---
    logger.info("Shutting down application...")
    await engine.dispose()
    logger.info("Database connection pool disposed")


def create_app() -> FastAPI:
    app = FastAPI(
        title="LINE OA <-> GoHighLevel Middleware",
        description="High-performance async middleware connecting LINE Official Account with GoHighLevel CRM.",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Middleware: Request Tracing
    app.add_middleware(TracingMiddleware)

    # Middleware: CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global Exception Handlers
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        trace_id = get_trace_id()
        logger.warn(
            "Request validation error",
            traceId=trace_id,
            errors=exc.errors(),
            body=exc.body,
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": "Validation Error",
                "details": exc.errors(),
                "traceId": trace_id,
            },
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        trace_id = get_trace_id()
        logger.warn(
            f"HTTP {exc.status_code} Exception: {exc.detail}",
            traceId=trace_id,
            status_code=exc.status_code,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.detail,
                "status_code": exc.status_code,
                "traceId": trace_id,
            },
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        trace_id = get_trace_id()
        logger.error(
            f"Unhandled internal server error: {exc}",
            traceId=trace_id,
            exc_info=True,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "Internal Server Error",
                "message": str(exc),
                "traceId": trace_id,
            },
        )

    # Register Routers
    app.include_router(health_router)
    app.include_router(oauth_router)
    app.include_router(webhooks_router)

    return app


app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=(settings.NODE_ENV == "development"),
        log_config=None,  # Use custom JSON structured logging
    )

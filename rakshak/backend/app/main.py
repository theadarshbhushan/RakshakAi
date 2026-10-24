"""
RakshakAI Multi-Tenant SaaS Backend.
Production-grade FastAPI application factory with Beanie ODM, Prometheus metrics,
rate limiting, security headers, per-tenant WebSockets, and structured logging.
"""
from contextlib import asynccontextmanager
import logging
from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi import HTTPException
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from prometheus_fastapi_instrumentator import Instrumentator

from app.core.config import settings
from app.core.logging import setup_logging, logger
from app.core.middleware import RequestIdAndSecurityHeadersMiddleware
from app.core.rate_limit import limiter
from app.core.errors import (
    AppError,
    app_error_handler,
    validation_error_handler,
    http_exception_handler,
    unhandled_exception_handler,
)
from app.core.security import decode_access_token
from app.models.user import User
from app.db.mongo import init_db, close_db
from app.jobs.scheduler import start_scheduler, stop_scheduler
from app.api.v1.api import api_v1_router
from app.realtime.ws import ws_hub


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager."""
    setup_logging()
    logger.info(f"Starting RakshakAI API [ENV={settings.ENV}, DETECTOR_MODE={settings.DETECTOR_MODE}] ...")

    # Validate production secrets
    settings.validate_prod_secrets()

    # Initialize Beanie ODM and MongoDB connection
    await init_db()

    # Start background scheduler for SLA escalations and retention
    start_scheduler()

    yield

    # Graceful shutdown
    logger.info("Shutting down RakshakAI API...")
    stop_scheduler()
    await close_db()
    logger.info("Shutdown complete.")


def create_app() -> FastAPI:
    """FastAPI Application Factory."""
    app = FastAPI(
        title="RakshakAI API",
        description="Production Multi-tenant SaaS AI Campus & Hostel Safety Platform - Explainable Incident Fusion",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/api/v1/openapi.json",
        lifespan=lifespan,
        swagger_ui_parameters={"persistAuthorization": True},
    )

    # 1. State & Rate Limiter
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # 2. Middlewares
    app.add_middleware(RequestIdAndSecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    # 3. Exception Handlers
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    # 4. Mount Master API v1 Router
    app.include_router(api_v1_router)

    # 5. Prometheus Metrics
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")

    # 6. WebSocket Endpoint with Per-Tenant Room Isolation
    @app.websocket("/api/v1/ws")
    async def websocket_endpoint(
        websocket: WebSocket,
        token: Optional[str] = Query(None),
    ):
        """
        Multi-tenant WebSocket endpoint.
        Requires valid bearer token in query parameter (?token=...) or first auth message.
        Authenticates user, validates token_version, and joins ONLY the user's organization room.
        Closes with 4401 if unauthorized.
        """
        # If token not in query, wait for first auth frame
        auth_token = token
        if not auth_token:
            await websocket.accept()
            try:
                first_msg = await websocket.receive_json()
                if first_msg.get("type") == "auth":
                    auth_token = first_msg.get("token")
            except Exception:
                await websocket.close(code=4401)
                return

        if not auth_token:
            await websocket.close(code=4401)
            return

        # Validate token
        try:
            payload = decode_access_token(auth_token)
            user_id = payload.get("sub")
            org_id = payload.get("org_id")
            token_version = payload.get("tv")
            user = await User.find_one({"_id": __import__("beanie").PydanticObjectId(user_id)})
            if not user or not user.is_active or user.token_version != token_version or user.org_id != org_id:
                await websocket.close(code=4401)
                return
        except Exception:
            await websocket.close(code=4401)
            return

        # Join tenant room
        # If connection was already accepted in handshake fallback, manage connection directly
        if not token:
            ws_hub.rooms.setdefault(org_id, []).append(websocket)
        else:
            await ws_hub.connect(org_id, websocket)

        try:
            while True:
                # Keepalive / ping-pong loop
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_text("pong")
        except WebSocketDisconnect:
            ws_hub.disconnect(org_id, websocket)
        except Exception:
            ws_hub.disconnect(org_id, websocket)

    @app.get("/", include_in_schema=False)
    async def root():
        return {
            "name": "RakshakAI API",
            "version": "1.0.0",
            "status": "operational",
            "docs": "/docs",
            "health": "/api/v1/health",
        }

    return app


app = create_app()

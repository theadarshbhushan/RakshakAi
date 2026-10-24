"""
FastAPI middlewares for Request-ID propagation, security headers, and structured access logging.
"""
import time
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import structlog
from app.core.config import settings

logger = structlog.get_logger("rakshakai.access")


class RequestIdAndSecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. Resolve Request ID
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        structlog.contextvars.bind_contextvars(request_id=request_id)

        start_time = time.perf_counter()

        # 2. Process Request
        try:
            response: Response = await call_next(request)
        except Exception:
            raise

        process_time_ms = round((time.perf_counter() - start_time) * 1000, 2)

        # 3. Add Response Security Headers
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'"

        if settings.ENV == "prod":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        # 4. Structured Access Log (skip health checks for noise reduction)
        path = request.url.path
        if not path.startswith("/api/v1/health") and path != "/metrics":
            logger.info(
                "http_request",
                method=request.method,
                path=path,
                status=response.status_code,
                duration_ms=process_time_ms,
                client_ip=request.client.host if request.client else "unknown",
            )

        structlog.contextvars.unbind_contextvars("request_id")
        return response

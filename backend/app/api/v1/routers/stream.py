"""
Live Camera MJPEG Streaming Router (/api/v1/stream).
Yields real-time multipart/x-mixed-replace MJPEG video streams from in-memory frame buffer:
- mode=skeleton (default): Accessible by any authenticated user. Accepts token via query param (?token=...).
- mode=blurred: Requires an active, unexpired break-glass token scoped to the camera's current incident.
  Strictly audits all accesses.
"""
import asyncio
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional

import cv2
import numpy as np
from beanie import PydanticObjectId
from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.core.errors import ForbiddenError, NotFoundError, UnauthorizedError
from app.core.security import decode_access_token, hash_token
from app.detectors.video_pose import latest_camera_frames
from app.models.incident import Incident
from app.models.privacy import BreakglassGrant
from app.models.user import User, utc_now
from app.models.zone import Camera
from app.repositories.repos import AuditRepository

router = APIRouter(prefix="/stream", tags=["Live Stream"])


def get_placeholder_frame(text: str = "RakshakAI Feed") -> bytes:
    """Generate simple fallback JPEG placeholder when camera has not emitted a frame yet."""
    canvas = np.zeros((360, 640, 3), dtype=np.uint8)
    cv2.putText(
        canvas,
        text,
        (160, 180),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 220, 255),
        2,
        cv2.LINE_AA,
    )
    _, jpg = cv2.imencode(".jpg", canvas)
    return jpg.tobytes()


async def authenticate_stream_request(
    request: Request,
    token_query: Optional[str] = None,
) -> User:
    """
    Authenticate streaming request.
    Supports either Authorization: Bearer <jwt> header OR ?token=<jwt> query parameter
    (since HTML <img> tags cannot send custom HTTP headers).
    """
    token = token_query
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1].strip()

    if not token:
        raise UnauthorizedError("Missing authentication token for stream", code="AUTH_MISSING_TOKEN")

    payload = decode_access_token(token)
    user_id = payload.get("sub")
    org_id = payload.get("org_id")
    if not user_id or not org_id:
        raise UnauthorizedError("Invalid token claims", code="AUTH_INVALID_TOKEN")

    try:
        user = await User.get(PydanticObjectId(user_id))
    except Exception:
        user = await User.find_one({"_id": user_id})

    if not user or user.org_id != org_id or not user.is_active:
        raise UnauthorizedError("Unauthorized user", code="AUTH_UNAUTHORIZED")

    return user


async def mjpeg_frame_generator(
    camera_id: str,
    mode: str = "skeleton",
) -> AsyncGenerator[bytes, None]:
    """Yield MJPEG frames separated by boundary=frame at ~10 FPS."""
    while True:
        cam_data = latest_camera_frames.get(camera_id, {})
        frame_bytes = cam_data.get(mode)

        if not frame_bytes:
            frame_bytes = get_placeholder_frame(f"Waiting for {camera_id}...")

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n"
            b"Content-Length: " + str(len(frame_bytes)).encode("ascii") + b"\r\n\r\n"
            + frame_bytes + b"\r\n"
        )
        await asyncio.sleep(0.1)


@router.get("/{camera_id}")
async def stream_camera(
    camera_id: str,
    request: Request,
    mode: str = Query("skeleton", description="skeleton | blurred"),
    token: Optional[str] = Query(None, description="Access token for <img> tags"),
    bg_token: Optional[str] = Query(None, description="Break-glass token for blurred mode"),
    x_breakglass_token: Optional[str] = Header(None, alias="X-Breakglass-Token"),
):
    """
    Live camera MJPEG stream.
    - mode=skeleton: Default privacy-preserving skeleton render. Any authenticated role.
    - mode=blurred: Face-blurred frame. Requires active break-glass grant for current camera incident.
    """
    # 1. Authenticate user
    current_user = await authenticate_stream_request(request, token_query=token)

    # 2. If blurred mode, enforce break-glass authorization
    if mode == "blurred":
        breakglass_val = x_breakglass_token or bg_token
        if not breakglass_val:
            raise UnauthorizedError(
                "Access to face-blurred live stream requires an active break-glass token.",
                code="AUTH_BREAKGLASS_REQUIRED",
            )

        token_h = hash_token(breakglass_val)
        now = utc_now()

        # Find camera to resolve its zone
        cam_doc = await Camera.find_one({"camera_id": camera_id, "org_id": current_user.org_id})
        zone_id = cam_doc.zone_id if cam_doc else camera_id

        # Find current active incident for this camera/zone
        active_incident = await Incident.find_one({
            "org_id": current_user.org_id,
            "zone_id": zone_id,
            "status": {"$in": ["new", "acknowledged", "investigating"]},
        })

        if not active_incident:
            raise NotFoundError("No active incident exists on this camera to justify break-glass stream access.")

        grant = await BreakglassGrant.find_one({
            "org_id": current_user.org_id,
            "token_hash": token_h,
            "incident_id": str(active_incident.id),
        })

        if not grant or (grant.expires_at and grant.expires_at.replace(tzinfo=timezone.utc) <= now):
            raise ForbiddenError("Break-glass token is invalid, expired, or not authorized for this camera incident.")

        # Tamper-evident audit log
        audit_repo = AuditRepository(current_user.org_id)
        await audit_repo.record_audit(
            actor={"type": "user", "id": str(current_user.id), "email": current_user.email},
            action="stream.blurred_accessed",
            target=f"camera:{camera_id}",
            reason=f"Break-glass live feed accessed for active incident {active_incident.id}.",
        )

    return StreamingResponse(
        mjpeg_frame_generator(camera_id, mode=mode),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )

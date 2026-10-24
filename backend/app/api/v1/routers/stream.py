"""
Live Camera MJPEG Streaming Router (/api/v1/stream).
Yields real-time multipart/x-mixed-replace MJPEG video streams from in-memory frame buffer:
- mode=skeleton (default): Accessible by any authenticated user. Accepts token via query param (?token=...).
- mode=blurred: Requires default blurred org setting, active emergency context, or break-glass grant.
- mode=emergency: Requires active emergency intruder reveal grant. Watermarks frames in real-time.
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
from app.fusion.corroboration import ensure_utc
from app.models.incident import Incident
from app.models.organization import Organization
from app.models.privacy import BreakglassGrant, EmergencyReveal
from app.models.user import User, utc_now
from app.models.zone import Camera
from app.privacy.encryption import apply_watermark_to_frame
from app.repositories.repos import AuditRepository

router = APIRouter(prefix="/stream", tags=["Live Stream"])


def get_placeholder_frame(text: str = "No live feed right now") -> bytes:
    """Generate simple fallback JPEG placeholder when camera has not emitted a frame yet."""
    canvas = np.zeros((360, 640, 3), dtype=np.uint8)
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.8
    thickness = 2
    size = cv2.getTextSize(text, font, font_scale, thickness)[0]
    x = max(20, (640 - size[0]) // 2)
    y = max(40, (360 + size[1]) // 2)
    cv2.putText(
        canvas,
        text,
        (x, y),
        font,
        font_scale,
        (180, 180, 180),
        thickness,
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
    viewer_email: str = "",
) -> AsyncGenerator[bytes, None]:
    """Yield MJPEG frames separated by boundary=frame at ~10 FPS."""
    while True:
        cam_data = latest_camera_frames.get(camera_id, {})
        lookup_mode = "blurred" if mode == "emergency" else mode
        frame_bytes = cam_data.get(lookup_mode)

        if not frame_bytes:
            frame_bytes = get_placeholder_frame("No live feed right now")
        elif mode == "emergency":
            # Overlay forensic watermark in real-time
            try:
                img_arr = np.frombuffer(frame_bytes, np.uint8)
                frame = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
                if frame is not None:
                    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                    frame = apply_watermark_to_frame(frame, viewer_email, now_str, "EMERGENCY ACCESS - RakshakAI")
                    _, out_jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    frame_bytes = out_jpg.tobytes()
            except Exception:
                pass

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
    mode: str = Query("skeleton", description="skeleton | blurred | emergency"),
    token: Optional[str] = Query(None, description="Access token for <img> tags"),
    bg_token: Optional[str] = Query(None, description="Break-glass token for blurred mode"),
    x_breakglass_token: Optional[str] = Header(None, alias="X-Breakglass-Token"),
):
    """
    Live camera MJPEG stream.
    - mode=skeleton: Default privacy-preserving skeleton render. Any authenticated role.
    - mode=blurred: Face-blurred frame. Requires default view, active emergency context, or breakglass grant.
    - mode=emergency: Targeted unblur with watermark. Requires active emergency reveal grant.
    """
    # 1. Authenticate user
    current_user = await authenticate_stream_request(request, token_query=token)

    # Rule: Auditors are restricted to skeleton view only
    if current_user.role == "auditor" and mode in ("blurred", "emergency"):
        raise ForbiddenError("Auditors are restricted to skeleton view only.", code="FORBIDDEN")

    # Find camera to resolve its zone
    cam_doc = await Camera.find_one({"camera_id": camera_id, "org_id": current_user.org_id})
    zone_id = cam_doc.zone_id if cam_doc else camera_id
    now = utc_now()

    # 2. If blurred mode, check authorization
    if mode == "blurred":
        org = await Organization.get(PydanticObjectId(current_user.org_id))
        org_default = org.settings.get("default_evidence_view", "skeleton") if org else "skeleton"
        is_authorized = (org_default == "blurred" and current_user.role in ("guard", "warden", "admin", "owner"))

        # Find current active incident for this camera/zone
        active_incident = await Incident.find_one({
            "org_id": current_user.org_id,
            "zone_id": zone_id,
            "status": {"$in": ["new", "acknowledged", "investigating"]},
        })

        if not is_authorized and active_incident:
            # Check Emergency Context View (C2)
            safety_kinds = {"fight", "distress_audio", "student_sos", "loitering"}
            if (active_incident.primary_kind in safety_kinds and
                    active_incident.severity in ("medium", "high", "critical")):
                last_ts = ensure_utc(active_incident.updated_ts or active_incident.created_ts)
                if (now - last_ts).total_seconds() <= 600:
                    is_authorized = True

            # Check break-glass grant
            if not is_authorized:
                breakglass_val = x_breakglass_token or bg_token
                if breakglass_val:
                    token_h = hash_token(breakglass_val)
                    grant = await BreakglassGrant.find_one({
                        "org_id": current_user.org_id,
                        "token_hash": token_h,
                        "incident_id": str(active_incident.id),
                    })
                    if grant and ensure_utc(grant.expires_at) > now:
                        is_authorized = True

                if not is_authorized:
                    user_grant = await BreakglassGrant.find_one({
                        "org_id": current_user.org_id,
                        "incident_id": str(active_incident.id),
                        "user_id": str(current_user.id),
                        "expires_at": {"$gt": now},
                    })
                    if user_grant:
                        is_authorized = True

        if not is_authorized:
            raise ForbiddenError(
                "Access to face-blurred live stream requires an active break-glass token or active emergency context.",
                code="BREAKGLASS_REQUIRED",
            )

        # Tamper-evident audit log
        audit_repo = AuditRepository(current_user.org_id)
        await audit_repo.record_audit(
            actor={"type": "user", "id": str(current_user.id), "email": current_user.email},
            action="stream.blurred_accessed",
            target=f"camera:{camera_id}",
            reason=f"Face-blurred live feed accessed for camera {camera_id}.",
        )

    # 3. If emergency mode, enforce active emergency reveal grant
    elif mode == "emergency":
        active_incident = await Incident.find_one({
            "org_id": current_user.org_id,
            "zone_id": zone_id,
            "status": {"$in": ["new", "acknowledged", "investigating"]},
        })
        if not active_incident:
            raise ForbiddenError(
                "No active incident in camera zone for emergency stream.",
                code="EMERGENCY_REVEAL_NOT_ELIGIBLE",
            )

        reveal = await EmergencyReveal.find_one({
            "org_id": current_user.org_id,
            "incident_id": str(active_incident.id),
            "expires_at": {"$gt": now},
        })
        if not reveal:
            raise ForbiddenError(
                "Emergency live stream requires an active emergency reveal grant.",
                code="EMERGENCY_REVEAL_NOT_ELIGIBLE",
            )

        audit_repo = AuditRepository(current_user.org_id)
        await audit_repo.record_audit(
            actor={"type": "user", "id": str(current_user.id), "email": current_user.email},
            action="stream.emergency_accessed",
            target=f"camera:{camera_id}",
            reason=f"Emergency live feed accessed with watermark under active reveal {reveal.id}.",
        )

    return StreamingResponse(
        mjpeg_frame_generator(camera_id, mode=mode, viewer_email=current_user.email),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )

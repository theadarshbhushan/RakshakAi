"""
Analyze API Router (/api/v1/analyze).
Supports on-demand security media upload & analysis, dual-modality video/audio,
annotated skeleton video streaming, and live webcam / RTSP camera analysis.
"""
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse

from beanie import PydanticObjectId
from app.core.config import settings
from app.core.deps import get_current_user, require_permission
from app.core.errors import BadRequestError, ForbiddenError, NotFoundError
from app.core.security import hash_token
from app.fusion.corroboration import ensure_utc
from app.models.analysis import AnalysisJob, utc_now
from app.models.organization import Organization
from app.models.privacy import BreakglassGrant
from app.models.user import User
from app.models.zone import Camera
from app.repositories.repos import AuditRepository
from app.schemas.domain import AnalysisJobResponse, LiveAnalysisRequest
from app.services.analysis_service import (
    cancel_analysis_job,
    run_media_analysis_job,
    save_uploaded_media,
    start_live_analysis,
    stop_live_analysis,
    validate_media_upload,
)

router = APIRouter(prefix="/analyze", tags=["Media Analysis"])


@router.post(
    "/upload",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=Dict[str, str],
    dependencies=[Depends(require_permission("scenarios:run"))],
)
async def upload_media_for_analysis(
    file: UploadFile = File(..., description="Video (mp4/avi/mov/mkv) or Audio (wav/mp3/m4a/flac) file"),
    camera_id: Optional[str] = Form(None, description="Required for video footage; determines zone and door line"),
    zone_id: Optional[str] = Form(None, description="Required for audio-only footage"),
    sim_start: Optional[str] = Form(None, description="Optional sim start time (e.g. 23:40 or 23:40:00) for night-time rules"),
    current_user: User = Depends(get_current_user),
):
    """
    Upload CCTV footage or audio recording for automated threat analysis.
    - Validates file extension AND content-type
    - Maximum size 200 MB (configurable)
    - Stores file under data/uploads/<org_id>/<job_id>/ with a randomized UUID
    - Initiates asynchronous background multi-modal analysis task
    - Returns job_id immediately
    """
    media_type, ext = validate_media_upload(file.filename, file.content_type)

    resolved_zone_id = zone_id
    if media_type == "video":
        if not camera_id:
            raise BadRequestError("camera_id is required for video analysis", code="VALIDATION_ERROR")
        # Lookup camera to determine zone
        cam = await Camera.find_one({"camera_id": camera_id, "org_id": current_user.org_id})
        if cam and not resolved_zone_id:
            resolved_zone_id = cam.zone_id
        if not resolved_zone_id:
            resolved_zone_id = "terrace"
    elif media_type == "audio":
        if not resolved_zone_id:
            raise BadRequestError("zone_id is required for audio-only analysis", code="VALIDATION_ERROR")

    new_job_id = uuid4().hex

    # Stream & save uploaded file
    saved_path = await save_uploaded_media(
        file=file,
        org_id=current_user.org_id,
        job_id=new_job_id,
        ext=ext,
    )

    # Create job document
    job = AnalysisJob(
        org_id=current_user.org_id,
        job_id=new_job_id,
        type=media_type,
        camera_id=camera_id,
        zone_id=resolved_zone_id,
        status="queued",
        progress=0,
        original_filename=file.filename,
        stored_path=str(saved_path),
        created_by=current_user.email,
        created_at=utc_now(),
    )
    await job.insert()

    # Record tamper-evident audit log
    audit_repo = AuditRepository(current_user.org_id)
    await audit_repo.record_audit(
        actor={"type": "user", "id": str(current_user.id), "email": current_user.email},
        action="analyze.upload",
        target=f"job:{new_job_id}",
        reason=f"Uploaded {file.filename} for {media_type} analysis (camera: {camera_id}, zone: {resolved_zone_id})",
    )

    # Launch background analysis task
    asyncio.create_task(
        run_media_analysis_job(
            job_id=new_job_id,
            org_id=current_user.org_id,
            sim_start_str=sim_start,
        )
    )

    return {"job_id": new_job_id}


@router.get(
    "/jobs",
    response_model=List[AnalysisJobResponse],
    dependencies=[Depends(require_permission("scenarios:run"))],
)
async def list_analysis_jobs(
    current_user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=100),
):
    """List all media analysis jobs for the authenticated organization."""
    jobs = await AnalysisJob.find(
        AnalysisJob.org_id == current_user.org_id
    ).sort(-AnalysisJob.created_at).limit(limit).to_list()
    return jobs


@router.get(
    "/jobs/{job_id}",
    response_model=AnalysisJobResponse,
    dependencies=[Depends(require_permission("scenarios:run"))],
)
async def get_analysis_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    """Retrieve detailed status and progress of a specific analysis job."""
    job = await AnalysisJob.find_one(
        AnalysisJob.job_id == job_id,
        AnalysisJob.org_id == current_user.org_id,
    )
    if not job:
        raise NotFoundError(f"Analysis job '{job_id}' not found")
    return job


@router.delete(
    "/jobs/{job_id}",
    response_model=Dict[str, str],
    dependencies=[Depends(require_permission("scenarios:run"))],
)
async def cancel_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    """Cancel an in-progress or queued analysis job."""
    job = await AnalysisJob.find_one(
        AnalysisJob.job_id == job_id,
        AnalysisJob.org_id == current_user.org_id,
    )
    if not job:
        raise NotFoundError(f"Analysis job '{job_id}' not found")

    if job.status in ("queued", "running"):
        cancel_analysis_job(job_id)
        job.status = "cancelled"
        job.completed_at = utc_now()
        await job.save()

    audit_repo = AuditRepository(current_user.org_id)
    await audit_repo.record_audit(
        actor={"type": "user", "id": str(current_user.id), "email": current_user.email},
        action="analyze.job_cancelled",
        target=f"job:{job_id}",
        reason="Analysis job cancelled by user",
    )

    return {"message": "Job cancelled successfully", "job_id": job_id}


@router.get(
    "/jobs/{job_id}/annotated",
)
async def get_annotated_video(
    job_id: str,
    mode: str = Query("skeleton", description="skeleton | blurred"),
    token: Optional[str] = Query(None, description="Break-glass token"),
    x_breakglass_token: Optional[str] = Header(None, alias="X-Breakglass-Token"),
    current_user: User = Depends(get_current_user),
):
    """
    Stream or download the privacy-preserving annotated skeleton or blurred MP4
    produced for a video analysis job.
    """
    job = await AnalysisJob.find_one(
        AnalysisJob.job_id == job_id,
        AnalysisJob.org_id == current_user.org_id,
    )
    if not job:
        raise NotFoundError(f"Analysis job '{job_id}' not found")

    if current_user.role == "auditor" and mode == "blurred":
        raise ForbiddenError("Auditors are restricted to skeleton view only.")

    if mode == "blurred":
        org = await Organization.get(PydanticObjectId(current_user.org_id))
        org_default = org.settings.get("default_evidence_view", "skeleton") if org else "skeleton"
        is_authorized = (org_default == "blurred" and current_user.role in ("guard", "warden", "admin", "owner"))

        if not is_authorized:
            now = utc_now()
            bg_val = x_breakglass_token or token
            if bg_val:
                tok_h = hash_token(bg_val)
                grant = await BreakglassGrant.find_one({
                    "org_id": current_user.org_id,
                    "token_hash": tok_h,
                    "job_id": job_id,
                })
                if grant and ensure_utc(grant.expires_at) > now:
                    is_authorized = True

            if not is_authorized:
                user_grant = await BreakglassGrant.find_one({
                    "org_id": current_user.org_id,
                    "job_id": job_id,
                    "user_id": str(current_user.id),
                    "expires_at": {"$gt": now},
                })
                if user_grant:
                    is_authorized = True

        if not is_authorized:
            raise ForbiddenError(
                "Access to blurred annotated video requires a break-glass token.",
                code="BREAKGLASS_REQUIRED",
            )

        mp4_path = settings.DATA_DIR / "evidence" / "restricted" / f"{job_id}_annotated_blurred.mp4"
        if not mp4_path.exists():
            # Fallback to public annotated if blurred was not generated
            mp4_path = settings.DATA_DIR / "evidence" / "public" / f"{job_id}_annotated.mp4"

        if not mp4_path.exists():
            raise NotFoundError(f"Blurred annotated output video for job '{job_id}' not found.")

        return FileResponse(
            path=str(mp4_path),
            media_type="video/mp4",
            filename=f"{job_id}_annotated_blurred.mp4",
        )

    # Default skeleton mode
    mp4_path = settings.DATA_DIR / "evidence" / "public" / f"{job_id}_annotated.mp4"
    if not mp4_path.exists():
        if job.annotated_video_path:
            alt_path = settings.DATA_DIR / job.annotated_video_path
            if alt_path.exists():
                mp4_path = alt_path

    if not mp4_path.exists():
        raise NotFoundError(f"Annotated output video for job '{job_id}' is not yet available or failed.")

    return FileResponse(
        path=str(mp4_path),
        media_type="video/mp4",
        filename=f"{job_id}_annotated.mp4",
    )


@router.post("/live")
async def start_live_stream_analysis(
    body: LiveAnalysisRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Start continuous live camera analysis from webcam or RTSP feed.
    Restricted to organization owners and administrators.
    """
    if current_user.role not in ("owner", "admin"):
        raise ForbiddenError("Only owner or admin can initiate live camera analysis", code="FORBIDDEN")

    cam = await Camera.find_one({"camera_id": body.camera_id, "org_id": current_user.org_id})
    if not cam:
        raise NotFoundError(f"Camera '{body.camera_id}' not found in organization")

    res = await start_live_analysis(
        org_id=current_user.org_id,
        camera_id=body.camera_id,
        source=body.source,
        mic_enabled=body.mic_enabled,
    )

    audit_repo = AuditRepository(current_user.org_id)
    await audit_repo.record_audit(
        actor={"type": "user", "id": str(current_user.id), "email": current_user.email},
        action="analyze.live_started",
        target=f"camera:{body.camera_id}",
        reason=f"Started continuous live analysis using source '{body.source}'",
    )

    return res


@router.post("/live/{camera_id}/stop")
async def stop_live_stream_analysis(
    camera_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Stop active continuous live camera analysis.
    Restricted to organization owners and administrators.
    """
    if current_user.role not in ("owner", "admin"):
        raise ForbiddenError("Only owner or admin can stop live camera analysis", code="FORBIDDEN")

    stopped = await stop_live_analysis(
        org_id=current_user.org_id,
        camera_id=camera_id,
    )

    audit_repo = AuditRepository(current_user.org_id)
    await audit_repo.record_audit(
        actor={"type": "user", "id": str(current_user.id), "email": current_user.email},
        action="analyze.live_stopped",
        target=f"camera:{camera_id}",
        reason="Stopped continuous live analysis",
    )

    return {"status": "stopped" if stopped else "not_found", "camera_id": camera_id}

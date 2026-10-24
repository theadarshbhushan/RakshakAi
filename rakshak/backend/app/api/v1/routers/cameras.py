"""
Cameras router (/api/v1/cameras).
Camera configuration with plan quota limit enforcement.
"""
from typing import List
from fastapi import APIRouter, Depends, status
from beanie import PydanticObjectId

from app.core.deps import get_current_user, require_permission
from app.core.errors import NotFoundError, ConflictError
from app.models.zone import Camera
from app.models.user import User
from app.services.org_service import OrgService
from app.schemas.organization import CameraCreateRequest, CameraResponse

router = APIRouter(prefix="/cameras", tags=["Cameras"])


@router.post("", response_model=CameraResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission("cameras:write"))])
async def create_camera(payload: CameraCreateRequest, current_user: User = Depends(get_current_user)):
    """Create a new security camera. Enforces plan max_cameras quota limit."""
    await OrgService.check_plan_limit(current_user.org_id, "camera")

    existing = await Camera.find_one({"org_id": current_user.org_id, "camera_id": payload.camera_id})
    if existing:
        raise ConflictError(f"Camera '{payload.camera_id}' already exists in this organization.", code="CAMERA_ALREADY_EXISTS")

    camera = Camera(
        org_id=current_user.org_id,
        site_id=payload.site_id,
        camera_id=payload.camera_id,
        name=payload.name,
        zone_id=payload.zone_id,
        source_path=payload.source_path,
        door_line=payload.door_line,
    )
    await camera.insert()

    return CameraResponse(
        id=str(camera.id),
        org_id=camera.org_id,
        site_id=camera.site_id,
        camera_id=camera.camera_id,
        name=camera.name,
        zone_id=camera.zone_id,
        source_path=camera.source_path,
        door_line=camera.door_line,
        status=camera.status,
        created_at=camera.created_at,
    )


@router.get("", response_model=List[CameraResponse], dependencies=[Depends(require_permission("cameras:read"))])
async def list_cameras(current_user: User = Depends(get_current_user)):
    """List all cameras registered in the organization."""
    cameras = await Camera.find(Camera.org_id == current_user.org_id).to_list()
    return [
        CameraResponse(
            id=str(c.id),
            org_id=c.org_id,
            site_id=c.site_id,
            camera_id=c.camera_id,
            name=c.name,
            zone_id=c.zone_id,
            source_path=c.source_path,
            door_line=c.door_line,
            status=c.status,
            created_at=c.created_at,
        )
        for c in cameras
    ]

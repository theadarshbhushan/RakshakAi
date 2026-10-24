"""
Zones router (/api/v1/zones).
Hostel zone security definitions and normalized polygon boundaries.
"""
from typing import List

from fastapi import APIRouter, Depends, status

from app.core.deps import get_current_user, require_permission
from app.core.errors import ConflictError, NotFoundError
from app.models.user import User
from app.models.zone import Zone
from app.schemas.organization import ZoneCreateRequest, ZoneResponse

router = APIRouter(prefix="/zones", tags=["Zones"])


@router.post("", response_model=ZoneResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission("zones:write"))])
async def create_zone(payload: ZoneCreateRequest, current_user: User = Depends(get_current_user)):
    """Create a new security zone within current organization."""
    existing = await Zone.find_one({"org_id": current_user.org_id, "zone_id": payload.zone_id})
    if existing:
        raise ConflictError(f"Zone '{payload.zone_id}' already exists in this organization.", code="ZONE_ALREADY_EXISTS")

    zone = Zone(
        org_id=current_user.org_id,
        site_id=payload.site_id,
        zone_id=payload.zone_id,
        name=payload.name,
        type=payload.type,
        polygons=payload.polygons,
        allowed_roles=payload.allowed_roles,
        adjacent_zone_ids=payload.adjacent_zone_ids,
        map_coords=payload.map_coords,
    )
    await zone.insert()

    return ZoneResponse(
        id=str(zone.id),
        org_id=zone.org_id,
        site_id=zone.site_id,
        zone_id=zone.zone_id,
        name=zone.name,
        type=zone.type,
        polygons=zone.polygons,
        allowed_roles=zone.allowed_roles,
        adjacent_zone_ids=zone.adjacent_zone_ids,
        map_coords=zone.map_coords,
        sos_token=zone.sos_token,
        created_at=zone.created_at,
    )


@router.get("", response_model=List[ZoneResponse], dependencies=[Depends(require_permission("zones:read"))])
async def list_zones(current_user: User = Depends(get_current_user)):
    """List all security zones for the current organization."""
    zones = await Zone.find(Zone.org_id == current_user.org_id).to_list()
    return [
        ZoneResponse(
            id=str(z.id),
            org_id=z.org_id,
            site_id=z.site_id,
            zone_id=z.zone_id,
            name=z.name,
            type=z.type,
            polygons=z.polygons,
            allowed_roles=z.allowed_roles,
            adjacent_zone_ids=z.adjacent_zone_ids,
            map_coords=z.map_coords,
            sos_token=z.sos_token,
            created_at=z.created_at,
        )
        for z in zones
    ]


@router.put("/{zone_id}", response_model=ZoneResponse, dependencies=[Depends(require_permission("zones:write"))])
async def update_zone(zone_id: str, payload: ZoneCreateRequest, current_user: User = Depends(get_current_user)):
    """Update zone properties and boundaries."""
    zone = await Zone.find_one({"org_id": current_user.org_id, "zone_id": zone_id})
    if not zone:
        raise NotFoundError("Zone", zone_id)

    zone.name = payload.name
    zone.type = payload.type
    zone.polygons = payload.polygons
    zone.allowed_roles = payload.allowed_roles
    zone.adjacent_zone_ids = payload.adjacent_zone_ids
    zone.map_coords = payload.map_coords
    await zone.save()

    return ZoneResponse(
        id=str(zone.id),
        org_id=zone.org_id,
        site_id=zone.site_id,
        zone_id=zone.zone_id,
        name=zone.name,
        type=zone.type,
        polygons=zone.polygons,
        allowed_roles=zone.allowed_roles,
        adjacent_zone_ids=zone.adjacent_zone_ids,
        map_coords=zone.map_coords,
        sos_token=zone.sos_token,
        created_at=zone.created_at,
    )

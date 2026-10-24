"""
Sites router (/api/v1/sites).
Campus buildings and hostel site management with plan limit enforcement.
"""
from typing import List

from fastapi import APIRouter, Depends, status

from app.core.deps import get_current_user, require_permission
from app.models.organization import Site
from app.models.user import User
from app.schemas.organization import SiteCreateRequest, SiteResponse
from app.services.org_service import OrgService

router = APIRouter(prefix="/sites", tags=["Sites"])


@router.post("", response_model=SiteResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission("sites:write"))])
async def create_site(payload: SiteCreateRequest, current_user: User = Depends(get_current_user)):
    """Create a new campus/hostel site. Enforces plan max_sites limit."""
    await OrgService.check_plan_limit(current_user.org_id, "site")

    site = Site(
        org_id=current_user.org_id,
        name=payload.name.strip(),
        address=payload.address,
        timezone=payload.timezone,
    )
    await site.insert()

    return SiteResponse(
        id=str(site.id),
        org_id=site.org_id,
        name=site.name,
        address=site.address,
        timezone=site.timezone,
        created_at=site.created_at,
    )


@router.get("", response_model=List[SiteResponse], dependencies=[Depends(require_permission("sites:read"))])
async def list_sites(current_user: User = Depends(get_current_user)):
    """List all sites for the current organization."""
    sites = await Site.find(Site.org_id == current_user.org_id).to_list()
    return [
        SiteResponse(
            id=str(s.id),
            org_id=s.org_id,
            name=s.name,
            address=s.address,
            timezone=s.timezone,
            created_at=s.created_at,
        )
        for s in sites
    ]

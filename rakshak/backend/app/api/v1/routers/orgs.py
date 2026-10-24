"""
Organization router (/api/v1/org).
Tenant details and SaaS plan upgrades.
"""
from fastapi import APIRouter, Depends
from beanie import PydanticObjectId

from app.core.deps import get_current_user, get_current_org, require_permission
from app.core.errors import AppError
from app.models.organization import Organization
from app.models.user import User
from app.repositories.repos import AuditRepository
from app.schemas.organization import OrgResponse, OrgPlanUpdateRequest
from app.services.org_service import PLANS

router = APIRouter(prefix="/org", tags=["Organizations"])


@router.get("", response_model=OrgResponse)
async def get_org_details(
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
):
    """Retrieve details and active plan of current organization."""
    return OrgResponse(
        id=str(org.id),
        name=org.name,
        slug=org.slug,
        plan=org.plan,
        created_at=org.created_at,
        settings=org.settings,
    )


@router.patch("/plan", response_model=OrgResponse, dependencies=[Depends(require_permission("billing:manage"))])
async def update_org_plan(
    payload: OrgPlanUpdateRequest,
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_org),
):
    """Update organization subscription plan (owner only)."""
    if payload.plan not in PLANS:
        raise AppError(f"Invalid plan '{payload.plan}'. Available plans: {list(PLANS.keys())}", status_code=400)

    old_plan = org.plan
    org.plan = payload.plan
    await org.save()

    audit_repo = AuditRepository(str(org.id))
    await audit_repo.record_audit(
        actor={"type": "user", "id": str(current_user.id), "email": current_user.email},
        action="org.plan_updated",
        target=f"organization:{org.id}",
        reason=f"Switched subscription plan from '{old_plan}' to '{org.plan}'.",
    )

    return OrgResponse(
        id=str(org.id),
        name=org.name,
        slug=org.slug,
        plan=org.plan,
        created_at=org.created_at,
        settings=org.settings,
    )

"""
Usage & Analytics router (/api/v1/usage).
Monitors subscription plan usage, quotas, and monthly incident metrics.
TODO [STABILIZATION]: Router disabled and unmounted in main app during stabilization.
"""
from datetime import datetime, timezone

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends

from app.core.deps import get_current_user
from app.models.incident import Incident
from app.models.organization import Organization, Site
from app.models.signal import Signal
from app.models.user import User
from app.models.zone import Camera
from app.schemas.domain import UsageResponse
from app.services.org_service import OrgService

router = APIRouter(prefix="/usage", tags=["Usage & Billing"])


@router.get("", response_model=UsageResponse)
async def get_usage_metrics(current_user: User = Depends(get_current_user)):
    """Retrieve current resource usage versus subscription plan limits."""
    org = await Organization.get(PydanticObjectId(current_user.org_id))
    limits = await OrgService.get_plan_limits(org.plan)

    # Current counts
    sites_cnt = await Site.find(Site.org_id == current_user.org_id).count()
    cameras_cnt = await Camera.find(Camera.org_id == current_user.org_id).count()
    users_cnt = await User.find(User.org_id == current_user.org_id, User.deleted_at == None).count()

    # Monthly activity counts
    now = datetime.now(timezone.utc)
    first_day_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    incidents_month = await Incident.find(
        Incident.org_id == current_user.org_id,
        Incident.created_ts >= first_day_of_month,
    ).count()

    signals_month = await Signal.find(
        Signal.org_id == current_user.org_id,
        Signal.ts >= first_day_of_month,
    ).count()

    return UsageResponse(
        plan=org.plan,
        limits=limits,
        current_counts={
            "sites": sites_cnt,
            "cameras": cameras_cnt,
            "users": users_cnt,
        },
        incidents_this_month=incidents_month,
        signals_this_month=signals_month,
    )

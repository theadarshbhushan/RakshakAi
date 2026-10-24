"""
Privacy & Evidence router (/api/v1/privacy and /api/v1/evidence).
Enforces break-glass emergency overrides, evidence retention purging, and privacy inventories.
Strictly ensures raw card IDs and biometric identities are never handled or leaked.
"""
from datetime import timedelta
from pathlib import Path
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, Query, Header, HTTPException, status
from fastapi.responses import FileResponse
from beanie import PydanticObjectId

from app.core.config import settings
from app.core.deps import get_current_user, require_permission
from app.core.security import generate_opaque_token, hash_token
from app.core.errors import UnauthorizedError, ForbiddenError, NotFoundError, AppError
from app.models.privacy import BreakglassGrant
from app.models.signal import Signal, AccessEvent
from app.models.incident import Incident
from app.models.organization import Organization
from app.models.user import User, utc_now
from app.repositories.repos import AuditRepository
from app.privacy.retention import execute_retention_purge, get_privacy_inventory
from app.services.org_service import OrgService
from app.schemas.domain import (
    BreakglassRequest,
    BreakglassResponse,
    PrivacySettingsRequest,
    PrivacyInventoryResponse,
)

router = APIRouter(tags=["Privacy & Evidence"])


# --- Breakglass & Retention ---
@router.post("/privacy/breakglass", response_model=BreakglassResponse, dependencies=[Depends(require_permission("evidence:breakglass"))])
async def request_breakglass_token(
    payload: BreakglassRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Emergency break-glass privacy override (owner/admin only).
    Issues a 10-minute token scoped to the specified incident.
    Stores only the SHA-256 token hash in the database and logs a tamper-evident audit entry.
    """
    if len(payload.reason.strip()) < 10:
        raise AppError("Break-glass justification reason must be at least 10 characters long.", status_code=400)

    # Verify incident exists and belongs to this tenant
    incident = await Incident.find_one({
        "_id": PydanticObjectId(payload.incident_id),
        "org_id": current_user.org_id,
    })
    if not incident:
        raise NotFoundError("Incident", payload.incident_id)

    raw_token = generate_opaque_token()
    token_h = hash_token(raw_token)
    expires_at = utc_now() + timedelta(minutes=10)

    grant = BreakglassGrant(
        org_id=current_user.org_id,
        incident_id=payload.incident_id,
        user_id=str(current_user.id),
        reason=payload.reason.strip(),
        token_hash=token_h,
        expires_at=expires_at,
    )
    await grant.insert()

    audit_repo = AuditRepository(current_user.org_id)
    await audit_repo.record_audit(
        actor={"type": "user", "id": str(current_user.id), "email": current_user.email},
        action="evidence.breakglass",
        target=f"incident:{incident.id}",
        reason=payload.reason.strip(),
    )

    return BreakglassResponse(
        token=raw_token,
        expires_at=expires_at,
        incident_id=payload.incident_id,
    )


@router.get("/evidence/{signal_id}")
async def get_evidence_file(
    signal_id: str,
    mode: str = Query("public", description="public | restricted"),
    token: Optional[str] = Query(None, description="Break-glass token for restricted evidence"),
    x_breakglass_token: Optional[str] = Header(None, alias="X-Breakglass-Token"),
    current_user: User = Depends(get_current_user),
):
    """
    Stream evidence file (audio clip or snapshot).
    Public evidence: accessible by authorized guards, wardens, admins.
    Restricted evidence: requires an active, unexpired 10-minute break-glass token scoped to the incident.
    """
    signal = await Signal.find_one({"_id": PydanticObjectId(signal_id), "org_id": current_user.org_id})
    if not signal:
        raise NotFoundError("Signal", signal_id)

    if not signal.evidence_path:
        raise NotFoundError("Evidence file has been purged or does not exist for this signal.")

    # Restricted mode validation
    if mode == "restricted":
        bg_token = x_breakglass_token or token
        if not bg_token:
            raise UnauthorizedError("Access to restricted evidence requires a valid break-glass token.", code="AUTH_BREAKGLASS_REQUIRED")

        token_h = hash_token(bg_token)
        now = utc_now()
        grant = await BreakglassGrant.find_one({
            "org_id": current_user.org_id,
            "token_hash": token_h,
            "incident_id": signal.incident_id,
            "expires_at": {"$gt": now},
        })
        if not grant:
            raise ForbiddenError("Break-glass token is invalid, expired, or not authorized for this incident.")

    # Locate evidence file on local disk
    evidence_path = Path(signal.evidence_path)
    if not evidence_path.is_absolute():
        evidence_path = settings.DATA_DIR / signal.evidence_path

    if not evidence_path.exists() or not evidence_path.is_file():
        raise NotFoundError(f"Evidence file on disk '{evidence_path.name}' not found.")

    return FileResponse(str(evidence_path))


@router.post("/privacy/purge", dependencies=[Depends(require_permission("privacy:manage"))])
async def trigger_retention_purge(current_user: User = Depends(get_current_user)):
    """
    Execute retention purge: delete evidence files older than retention_days,
    null evidence_path pointers, and log audit summary.
    """
    summary = await execute_retention_purge(user=current_user.email)
    return summary


@router.get("/privacy/inventory", response_model=PrivacyInventoryResponse, dependencies=[Depends(require_permission("privacy:manage"))])
async def get_inventory(current_user: User = Depends(get_current_user)):
    """Return inventory of stored evidence files and document counts."""
    inventory = await get_privacy_inventory()
    return inventory


@router.get("/privacy/settings", dependencies=[Depends(require_permission("privacy:manage"))])
async def get_privacy_settings(current_user: User = Depends(get_current_user)):
    """Retrieve data retention and privacy settings."""
    org = await Organization.get(PydanticObjectId(current_user.org_id))
    return {
        "retention_days": org.settings.get("retention_days", 7),
        "plan": org.plan,
        "max_retention_days": (await OrgService.get_plan_limits(org.plan)).get("retention_days_max", 7),
    }


@router.put("/privacy/settings", dependencies=[Depends(require_permission("privacy:manage"))])
async def update_privacy_settings(
    payload: PrivacySettingsRequest,
    current_user: User = Depends(get_current_user),
):
    """Update data retention settings, bounded by subscription plan limit."""
    org = await Organization.get(PydanticObjectId(current_user.org_id))
    plan_limits = await OrgService.get_plan_limits(org.plan)
    max_days = plan_limits.get("retention_days_max", 7)

    if payload.retention_days > max_days:
        raise AppError(
            f"Retention days exceeds maximum allowed for '{org.plan}' plan ({max_days} days).",
            status_code=400,
        )

    org.settings["retention_days"] = payload.retention_days
    await org.save()

    audit_repo = AuditRepository(current_user.org_id)
    await audit_repo.record_audit(
        actor={"type": "user", "id": str(current_user.id), "email": current_user.email},
        action="privacy.settings_updated",
        target=f"organization:{org.id}",
        reason=f"Updated evidence retention days to {payload.retention_days}.",
    )

    return {"message": "Retention settings updated", "retention_days": payload.retention_days}

"""
Rules router (/api/v1/rules).
Tenant-scoped versioned rules management (curfew, zone permissions, thresholds, windows).
"""
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends

from app.core.deps import get_current_user, require_permission
from app.core.errors import NotFoundError
from app.models.rules import RuleDocument, utc_now
from app.models.user import User
from app.repositories.repos import AuditRepository

router = APIRouter(prefix="/rules", tags=["Rules"])


@router.get("", response_model=Dict[str, Any], dependencies=[Depends(require_permission("rules:read"))])
async def get_rules(current_user: User = Depends(get_current_user)):
    """Retrieve the currently active versioned rules configuration for the tenant."""
    rule_doc = await RuleDocument.find_one({"org_id": current_user.org_id, "is_active": True})
    if not rule_doc:
        raise NotFoundError("Rule configuration for tenant", current_user.org_id)

    return {
        "version": rule_doc.version,
        "curfew": rule_doc.curfew,
        "zones": rule_doc.zones,
        "tailgating": rule_doc.tailgating,
        "fusion": rule_doc.fusion,
        "weights": rule_doc.weights,
        "updated_at": rule_doc.updated_at.isoformat(),
        "updated_by": rule_doc.updated_by,
    }


@router.put("", response_model=Dict[str, Any], dependencies=[Depends(require_permission("rules:write"))])
async def update_rules(
    payload: Dict[str, Any] = Body(...),
    current_user: User = Depends(get_current_user),
):
    """
    Update rules configuration. Creates a new version and archives the previous version.
    """
    active_doc = await RuleDocument.find_one({"org_id": current_user.org_id, "is_active": True})
    next_version = (active_doc.version + 1) if active_doc else 1

    if active_doc:
        active_doc.is_active = False
        await active_doc.save()

    new_rule_doc = RuleDocument(
        org_id=current_user.org_id,
        version=next_version,
        curfew=payload.get("curfew", active_doc.curfew if active_doc else {}),
        zones=payload.get("zones", active_doc.zones if active_doc else {}),
        tailgating=payload.get("tailgating", active_doc.tailgating if active_doc else {}),
        fusion=payload.get("fusion", active_doc.fusion if active_doc else {}),
        weights=payload.get("weights", active_doc.weights if active_doc else {}),
        updated_by=current_user.email,
        updated_at=utc_now(),
        is_active=True,
    )
    await new_rule_doc.insert()

    audit_repo = AuditRepository(current_user.org_id)
    await audit_repo.record_audit(
        actor={"type": "user", "id": str(current_user.id), "email": current_user.email},
        action="rules.updated",
        target=f"rules:v{next_version}",
        reason=f"Updated rules configuration to version {next_version}.",
    )

    return {
        "message": f"Rules updated to version {next_version}",
        "version": new_rule_doc.version,
        "curfew": new_rule_doc.curfew,
        "zones": new_rule_doc.zones,
        "tailgating": new_rule_doc.tailgating,
        "fusion": new_rule_doc.fusion,
        "weights": new_rule_doc.weights,
    }

"""
Calibration router (/api/v1/calibration).
Inspect detector sensitivity thresholds and revert auto-calibration history adjustments.
"""
from typing import List, Dict, Any
from fastapi import APIRouter, Depends
from beanie import PydanticObjectId

from app.core.deps import get_current_user, require_permission
from app.models.incident import ThresholdHistory
from app.models.rules import RuleDocument
from app.models.user import User
from app.services.incident_service import IncidentService
from app.schemas.domain import (
    ThresholdHistoryResponse,
    CalibrationOverviewResponse,
)

router = APIRouter(prefix="/calibration", tags=["Calibration"])


@router.get("", response_model=CalibrationOverviewResponse, dependencies=[Depends(require_permission("calibration:read"))])
async def get_calibration_overview(current_user: User = Depends(get_current_user)):
    """Retrieve current detector thresholds per zone and calibration history log."""
    active_rules = await RuleDocument.find_one({"org_id": current_user.org_id, "is_active": True})
    thresholds_by_zone = {}
    if active_rules and active_rules.zones:
        for zid, zconf in active_rules.zones.items():
            thresholds_by_zone[zid] = zconf.get("thresholds", {})

    history = await ThresholdHistory.find(
        ThresholdHistory.org_id == current_user.org_id
    ).sort("-_id").limit(100).to_list()

    history_resp = [
        ThresholdHistoryResponse(
            id=str(h.id),
            zone_id=h.zone_id,
            detector=h.detector,
            old_value=h.old_value,
            new_value=h.new_value,
            reason=h.reason,
            ts=h.ts,
            reverted=h.reverted,
            changed_by=h.changed_by,
        )
        for h in history
    ]

    return CalibrationOverviewResponse(
        thresholds=thresholds_by_zone,
        history=history_resp,
    )


@router.post("/{history_id}/revert", dependencies=[Depends(require_permission("calibration:revert"))])
async def revert_threshold(history_id: str, current_user: User = Depends(get_current_user)):
    """Revert a calibration threshold modification back to its previous value."""
    history = await IncidentService.revert_calibration(current_user.org_id, history_id, current_user)
    return {
        "message": f"Successfully reverted threshold for {history.zone_id}/{history.detector} to {history.old_value}",
        "id": str(history.id),
        "reverted": history.reverted,
    }

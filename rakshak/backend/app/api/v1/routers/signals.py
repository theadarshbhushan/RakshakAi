"""
Signals router (/api/v1/signals).
Query individual video, audio, and access control detector signals.
"""
from typing import Any, Dict, Optional

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, Query

from app.core.deps import get_current_user, require_permission
from app.models.signal import Signal
from app.models.user import User
from app.privacy.pseudonymize import sanitize_for_api
from app.schemas.domain import PaginatedResponse, SignalResponse

router = APIRouter(prefix="/signals", tags=["Signals"])


@router.get("", response_model=PaginatedResponse[SignalResponse], dependencies=[Depends(require_permission("signals:read"))])
async def list_signals(
    current_user: User = Depends(get_current_user),
    modality: Optional[str] = Query(None, description="video | audio | access"),
    kind: Optional[str] = Query(None),
    zone_id: Optional[str] = Query(None),
    suppressed: Optional[bool] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    cursor: Optional[str] = Query(None),
):
    """List signals within current organization, including suppressed ones."""
    query: Dict[str, Any] = {"org_id": current_user.org_id}
    if modality:
        query["modality"] = modality
    if kind:
        query["kind"] = kind
    if zone_id:
        query["zone_id"] = zone_id
    if suppressed is not None:
        query["suppressed"] = suppressed
    if cursor:
        try:
            query["_id"] = {"$lt": PydanticObjectId(cursor)}
        except Exception:
            pass

    signals = await Signal.find(query).sort("-_id").limit(limit + 1).to_list()
    has_next = len(signals) > limit
    items_to_return = signals[:limit]
    next_cursor = str(items_to_return[-1].id) if has_next and items_to_return else None

    resp_items = [
        SignalResponse(
            id=str(s.id),
            org_id=s.org_id,
            site_id=s.site_id,
            ts=s.ts,
            modality=s.modality,
            kind=s.kind,
            zone_id=s.zone_id,
            camera_id=s.camera_id,
            score=s.score,
            threshold=s.threshold,
            details=sanitize_for_api(s.details),
            suppressed=s.suppressed,
            suppress_reason=s.suppress_reason,
            evidence_path=s.evidence_path,
            incident_id=s.incident_id,
            source=s.source,
        )
        for s in items_to_return
    ]

    return PaginatedResponse(items=resp_items, next_cursor=next_cursor)

"""
Incidents router (/api/v1/incidents).
Incident triage, explainability, acknowledgment, and human review.
"""
from datetime import timedelta
from typing import Any, Dict, Optional

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, Query

from app.core.deps import get_current_user, require_permission
from app.core.errors import NotFoundError
from app.models.incident import Incident
from app.models.signal import AccessEvent, Signal
from app.models.user import User
from app.privacy.pseudonymize import sanitize_for_api
from app.schemas.domain import (
    IncidentResponse,
    IncidentReviewRequest,
    PaginatedResponse,
    SignalResponse,
)
from app.services.incident_service import IncidentService

router = APIRouter(prefix="/incidents", tags=["Incidents"])


@router.get("", response_model=PaginatedResponse[IncidentResponse], dependencies=[Depends(require_permission("incidents:read"))])
async def list_incidents(
    current_user: User = Depends(get_current_user),
    status: Optional[str] = Query(None, description="new | acknowledged | investigating | confirmed | false_alarm"),
    severity: Optional[str] = Query(None, description="low | medium | high | critical"),
    zone_id: Optional[str] = Query(None),
    site_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    cursor: Optional[str] = Query(None, description="Cursor for pagination (ObjectId string)"),
):
    """
    List incidents with filtering by status, severity, zone, and site.
    Strictly isolated to current organization.
    """
    query: Dict[str, Any] = {"org_id": current_user.org_id}
    if status:
        query["status"] = status
    if severity:
        query["severity"] = severity
    if zone_id:
        query["zone_id"] = zone_id
    if site_id:
        query["site_id"] = site_id
    if cursor:
        try:
            query["_id"] = {"$lt": PydanticObjectId(cursor)}
        except Exception:
            pass

    incidents = await Incident.find(query).sort("-_id").limit(limit + 1).to_list()
    has_next = len(incidents) > limit
    items_to_return = incidents[:limit]
    next_cursor = str(items_to_return[-1].id) if has_next and items_to_return else None

    resp_items = [
        IncidentResponse(
            id=str(inc.id),
            org_id=inc.org_id,
            site_id=inc.site_id,
            created_ts=inc.created_ts,
            updated_ts=inc.updated_ts,
            zone_id=inc.zone_id,
            severity=inc.severity,
            composite_score=inc.composite_score,
            modalities=inc.modalities,
            signal_ids=inc.signal_ids,
            explanation=inc.explanation,
            status=inc.status,
            acknowledged_by=inc.acknowledged_by,
            acknowledged_ts=inc.acknowledged_ts,
            escalated=inc.escalated,
            reviewer=inc.reviewer,
            review_note=inc.review_note,
            reviewed_ts=inc.reviewed_ts,
        )
        for inc in items_to_return
    ]

    return PaginatedResponse(items=resp_items, next_cursor=next_cursor)


@router.get("/{incident_id}", response_model=IncidentResponse, dependencies=[Depends(require_permission("incidents:read"))])
async def get_incident(incident_id: str, current_user: User = Depends(get_current_user)):
    """
    Get full incident details with attached signals and corroborated access events.
    Returns 404 if incident belongs to another tenant.
    """
    incident = await Incident.find_one({"_id": PydanticObjectId(incident_id), "org_id": current_user.org_id})
    if not incident:
        raise NotFoundError("Incident", incident_id)

    # Fetch signals
    signals_list = []
    if incident.signal_ids:
        obj_ids = [PydanticObjectId(sid) for sid in incident.signal_ids if len(sid) == 24]
        fetched_signals = await Signal.find({"_id": {"$in": obj_ids}, "org_id": current_user.org_id}).to_list()
        for s in fetched_signals:
            signals_list.append(
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
            )

    # Fetch related access events in this zone around the incident timeframe
    start_window = incident.created_ts - timedelta(minutes=5)
    end_window = incident.updated_ts + timedelta(minutes=5)
    access_events = await AccessEvent.find({
        "org_id": current_user.org_id,
        "zone_id": incident.zone_id,
        "ts": {"$gte": start_window, "$lte": end_window},
    }).limit(20).to_list()

    access_events_data = [
        {
            "id": str(e.id),
            "ts": e.ts.isoformat(),
            "pseudo_id": e.pseudo_id,
            "role": e.role,
            "door_id": e.door_id,
            "direction": e.direction,
            "result": e.result,
        }
        for e in access_events
    ]

    return IncidentResponse(
        id=str(incident.id),
        org_id=incident.org_id,
        site_id=incident.site_id,
        created_ts=incident.created_ts,
        updated_ts=incident.updated_ts,
        zone_id=incident.zone_id,
        severity=incident.severity,
        composite_score=incident.composite_score,
        modalities=incident.modalities,
        signal_ids=incident.signal_ids,
        explanation=incident.explanation,
        status=incident.status,
        acknowledged_by=incident.acknowledged_by,
        acknowledged_ts=incident.acknowledged_ts,
        escalated=incident.escalated,
        reviewer=incident.reviewer,
        review_note=incident.review_note,
        reviewed_ts=incident.reviewed_ts,
        signals=signals_list,
        access_events=access_events_data,
    )


@router.post("/{incident_id}/ack", dependencies=[Depends(require_permission("incidents:ack"))])
async def acknowledge_incident(incident_id: str, current_user: User = Depends(get_current_user)):
    """Acknowledge an incident."""
    incident = await IncidentService.acknowledge_incident(current_user.org_id, incident_id, current_user)
    return {
        "message": "Incident acknowledged",
        "id": str(incident.id),
        "status": incident.status,
        "acknowledged_by": incident.acknowledged_by,
        "acknowledged_ts": incident.acknowledged_ts.isoformat() if incident.acknowledged_ts else None,
    }


@router.post("/{incident_id}/review", dependencies=[Depends(require_permission("incidents:review"))])
async def review_incident(
    incident_id: str,
    payload: IncidentReviewRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Review an incident: confirmed | false_alarm | investigating.
    On false_alarm, automatically triggers calibration threshold adjustment (+0.05).
    """
    incident = await IncidentService.review_incident(
        org_id=current_user.org_id,
        incident_id=incident_id,
        label=payload.label,
        note=payload.note,
        user=current_user,
    )
    return {
        "message": f"Incident reviewed as {incident.status}",
        "id": str(incident.id),
        "status": incident.status,
        "reviewer": incident.reviewer,
        "review_note": incident.review_note,
        "reviewed_ts": incident.reviewed_ts.isoformat() if incident.reviewed_ts else None,
    }

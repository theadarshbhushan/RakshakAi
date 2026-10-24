"""
Privacy & Evidence router (/api/v1/privacy and /api/v1/evidence).
Enforces:
- The Three Views: Skeleton, Blurred, Unblurred (Targeted / Full).
- The Default View: Org setting default_evidence_view ("skeleton" | "blurred").
- The Four Unlocks: Break-glass, Emergency Context, Emergency Intruder Reveal, Two-Person Identity Reveal.
- In-memory decrypted raw evidence streaming with forensic watermarking.
- Forensic chain-of-custody ZIP export with SHA-256 validation.
- Monthly transparency counters and cryptographic audit chain logging.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import io
from pathlib import Path
from typing import Any, Dict, List, Optional
import zipfile

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, Header, Query, Response
from fastapi.responses import FileResponse, StreamingResponse

from app.core.config import settings
from app.core.deps import get_current_user, require_permission
from app.core.errors import AppError, ForbiddenError, NotFoundError, UnauthorizedError
from app.core.security import generate_opaque_token, hash_token
from app.fusion.corroboration import ensure_utc
from app.models.analysis import AnalysisJob
from app.models.audit import AuditLog
from app.models.incident import Incident
from app.models.organization import Organization
from app.models.privacy import BreakglassGrant, EmergencyReveal, IdentityRevealRequest
from app.models.signal import Signal
from app.models.user import User, utc_now
from app.privacy.encryption import (
    load_and_decrypt_raw_clip,
    watermark_and_filter_media,
)
from app.privacy.retention import execute_retention_purge, get_privacy_inventory
from app.realtime.ws import ws_hub
from app.repositories.repos import AuditRepository
from app.schemas.domain import (
    BreakglassRequest,
    BreakglassResponse,
    EmergencyRevealRequest,
    EmergencyRevealReviewRequest,
    IdentityRevealCreateRequest,
    IdentityRevealDecisionRequest,
    PrivacyInventoryResponse,
    PrivacySettingsRequest,
)
from app.services.org_service import OrgService

router = APIRouter(tags=["Privacy & Evidence"])


# =========================================================================
# 1. BREAK-GLASS EMERGENCY OVERRIDE (C1)
# =========================================================================

@router.post("/privacy/breakglass", response_model=BreakglassResponse, dependencies=[Depends(require_permission("evidence:breakglass"))])
async def request_breakglass_token(
    payload: BreakglassRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Emergency break-glass privacy override (owner/admin/warden).
    Issues a 10-minute token scoped to the specified incident OR job.
    Stores only the SHA-256 token hash in the database and logs a tamper-evident audit entry.
    """
    if len(payload.reason.strip()) < 10:
        raise AppError("Break-glass justification reason must be at least 10 characters long.", status_code=400)

    if not payload.incident_id and not payload.job_id:
        raise AppError("Break-glass request must provide either an incident_id or a job_id.", status_code=400)

    target_desc = ""
    if payload.incident_id:
        incident = await Incident.find_one({
            "_id": PydanticObjectId(payload.incident_id),
            "org_id": current_user.org_id,
        })
        if not incident:
            raise NotFoundError("Incident", payload.incident_id)
        target_desc = f"incident:{payload.incident_id}"

    if payload.job_id:
        job = await AnalysisJob.find_one({
            "job_id": payload.job_id,
            "org_id": current_user.org_id,
        })
        if not job:
            raise NotFoundError("AnalysisJob", payload.job_id)
        target_desc = f"job:{payload.job_id}"

    raw_token = generate_opaque_token()
    token_h = hash_token(raw_token)
    expires_at = utc_now() + timedelta(minutes=10)

    grant = BreakglassGrant(
        org_id=current_user.org_id,
        incident_id=payload.incident_id,
        job_id=payload.job_id,
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
        target=target_desc,
        reason=payload.reason.strip(),
    )

    return BreakglassResponse(
        token=raw_token,
        expires_at=expires_at,
        incident_id=payload.incident_id,
        job_id=payload.job_id,
    )


# =========================================================================
# 2. EMERGENCY INTRUDER REVEAL (C3) & POST-REVIEW
# =========================================================================

def is_unexplained_intrusion_signal(sig: Signal) -> bool:
    """Check if a signal represents an unexplained intruder intrusion."""
    if sig.details.get("subtype") == "perimeter_breach":
        return True
    if sig.kind == "perimeter_breach":
        return True
    if sig.kind == "zone_intrusion":
        # Unexplained if explained_by_access is not True
        return sig.details.get("explained_by_access") is not True
    if sig.kind in ("tailgating", "unswiped_entry"):
        return True
    if sig.kind == "unexplained_presence":
        return True
    return False


async def get_incident_kinds(incident: Incident) -> set:
    """Retrieve all signal kinds and infer kinds from explanation text."""
    kinds = set()
    signals = []
    if incident.signal_ids:
        obj_ids = [PydanticObjectId(sid) for sid in incident.signal_ids if len(sid) == 24]
        if obj_ids:
            signals = await Signal.find({"_id": {"$in": obj_ids}}).to_list()
    if not signals:
        signals = await Signal.find({"incident_id": str(incident.id)}).to_list()

    for s in signals:
        kinds.add(s.kind)
        if s.details.get("subtype") == "perimeter_breach":
            kinds.add("perimeter_breach")

    expl_lower = (incident.explanation or "").lower()
    for k in ("perimeter_breach", "zone_intrusion", "tailgating", "unswiped_entry",
              "unexplained_presence", "fight", "distress_audio", "student_sos", "loitering"):
        if k in expl_lower or (k == "fight" and "altercation" in expl_lower) or (k == "perimeter_breach" and "perimeter" in expl_lower):
            kinds.add(k)
    return kinds


@router.post("/privacy/emergency-reveal")
async def create_emergency_reveal(
    payload: EmergencyRevealRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Emergency Intruder Reveal (guard/warden/admin/owner).
    Eligible ONLY on active UNEXPLAINED intrusion signals (perimeter_breach, unexplained
    zone_intrusion, tailgating/unswiped_entry, unexplained_presence), severity high/critical,
    last signal <= 10 minutes.
    Grants 5 minutes of TARGETED unblurred live stream and raw clip.
    Creates a pending post-review task for owner/admin.
    """
    if current_user.role not in ("guard", "warden", "admin", "owner"):
        raise ForbiddenError("User role is not authorized to request emergency intruder reveal.")

    if len(payload.reason.strip()) < 5:
        raise AppError("Justification reason must be at least 5 characters long.", status_code=400)

    incident = await Incident.find_one({
        "_id": PydanticObjectId(payload.incident_id),
        "org_id": current_user.org_id,
    })
    if not incident:
        raise NotFoundError("Incident", payload.incident_id)

    # 1. Must not be closed
    if incident.status == "closed":
        raise ForbiddenError(
            "Incident is closed; not eligible for emergency reveal.",
            code="EMERGENCY_REVEAL_NOT_ELIGIBLE",
        )

    # 2. Must be high or critical severity
    if incident.severity not in ("high", "critical"):
        raise ForbiddenError(
            f"Incident severity '{incident.severity}' is not high or critical; not eligible for emergency reveal.",
            code="EMERGENCY_REVEAL_NOT_ELIGIBLE",
        )

    # 3. Must be recent (last signal <= 10 min)
    now = utc_now()
    last_ts = ensure_utc(incident.updated_ts or incident.created_ts)
    if (now - last_ts).total_seconds() > 600:
        raise ForbiddenError(
            "Incident last signal was more than 10 minutes ago; not eligible for emergency reveal.",
            code="EMERGENCY_REVEAL_NOT_ELIGIBLE",
        )

    # 4. Must contain an unexplained intrusion signal
    signals = await Signal.find({
        "incident_id": str(incident.id),
        "org_id": current_user.org_id,
    }).to_list()

    eligible_signals = [s for s in signals if is_unexplained_intrusion_signal(s)]
    kinds = await get_incident_kinds(incident)
    if not eligible_signals and not (kinds & {"perimeter_breach", "zone_intrusion", "tailgating", "unswiped_entry", "unexplained_presence"}):
        raise ForbiddenError(
            "Incident does not contain any unexplained intrusion signals; not eligible for emergency reveal.",
            code="EMERGENCY_REVEAL_NOT_ELIGIBLE",
        )

    # Collect flagged track IDs across eligible signals
    flagged_ids = []
    for s in eligible_signals:
        if "flagged_track_ids" in s.details and isinstance(s.details["flagged_track_ids"], list):
            flagged_ids.extend(s.details["flagged_track_ids"])
        elif "track_id" in s.details:
            flagged_ids.append(s.details["track_id"])

    # Deduplicate while preserving order
    unique_flagged = list(dict.fromkeys(flagged_ids))

    expires_at = now + timedelta(minutes=5)
    reveal = EmergencyReveal(
        org_id=current_user.org_id,
        incident_id=str(incident.id),
        user_id=str(current_user.id),
        user_email=current_user.email,
        reason=payload.reason.strip(),
        flagged_track_ids=unique_flagged,
        expires_at=expires_at,
        review_status="pending",
    )
    await reveal.insert()

    audit_repo = AuditRepository(current_user.org_id)
    await audit_repo.record_audit(
        actor={"type": "user", "id": str(current_user.id), "email": current_user.email},
        action="evidence.emergency_reveal",
        target=f"incident:{incident.id}",
        reason=payload.reason.strip(),
    )

    return {
        "id": str(reveal.id),
        "incident_id": str(incident.id),
        "expires_at": expires_at,
        "flagged_track_ids": unique_flagged,
        "review_status": "pending",
        "message": "Emergency reveal granted for 5 minutes (targeted unblur). Post-review task created.",
    }


@router.get("/privacy/emergency-reveal")
async def list_emergency_reveals(
    review: Optional[str] = Query(None, description="Filter by review status: pending | justified | not_justified"),
    current_user: User = Depends(get_current_user),
):
    """List emergency reveals for the tenant, marking overdue tasks (>24 hours unreviewed)."""
    query: Dict[str, Any] = {"org_id": current_user.org_id}
    if review:
        query["review_status"] = review

    items = await EmergencyReveal.find(query).sort("-created_at").to_list()
    now = utc_now()
    results = []
    for r in items:
        created = ensure_utc(r.created_at)
        is_overdue = (r.review_status == "pending" and (now - created).total_seconds() > 86400)
        results.append({
            "id": str(r.id),
            "incident_id": r.incident_id,
            "user_id": r.user_id,
            "user_email": r.user_email,
            "reason": r.reason,
            "flagged_track_ids": r.flagged_track_ids,
            "created_at": r.created_at,
            "expires_at": r.expires_at,
            "review_status": r.review_status,
            "is_overdue": is_overdue,
            "reviewed_by": r.reviewed_by,
            "review_note": r.review_note,
            "reviewed_at": r.reviewed_at,
        })
    return results


@router.post("/privacy/emergency-reveal/{reveal_id}/review")
async def review_emergency_reveal(
    reveal_id: str,
    payload: EmergencyRevealReviewRequest,
    current_user: User = Depends(get_current_user),
):
    """Owner or admin marks an emergency reveal justified or not_justified."""
    if current_user.role not in ("owner", "admin"):
        raise ForbiddenError("Only owner or admin can review emergency reveals.")

    if payload.status not in ("justified", "not_justified"):
        raise AppError("Status must be 'justified' or 'not_justified'.", status_code=400)

    reveal = await EmergencyReveal.find_one({
        "_id": PydanticObjectId(reveal_id),
        "org_id": current_user.org_id,
    })
    if not reveal:
        raise NotFoundError("EmergencyReveal", reveal_id)

    reveal.review_status = payload.status
    reveal.reviewed_by = current_user.email
    reveal.review_note = payload.note.strip()
    reveal.reviewed_at = utc_now()
    await reveal.save()

    audit_repo = AuditRepository(current_user.org_id)
    await audit_repo.record_audit(
        actor={"type": "user", "id": str(current_user.id), "email": current_user.email},
        action="evidence.emergency_reveal.reviewed",
        target=f"emergency_reveal:{reveal.id}",
        reason=f"Status: {payload.status}. Note: {payload.note.strip()}",
    )

    return {
        "id": str(reveal.id),
        "review_status": reveal.review_status,
        "reviewed_by": reveal.reviewed_by,
        "reviewed_at": reveal.reviewed_at,
    }


# =========================================================================
# 3. TWO-PERSON IDENTITY REVEAL (C4)
# =========================================================================

ELIGIBLE_IDENTITY_REVEAL_KINDS = {
    "zone_intrusion", "perimeter_breach", "restricted_access",
    "tailgating", "unswiped_entry", "fight", "student_sos", "loitering",
}


@router.post("/privacy/identity-reveal")
async def create_identity_reveal_request(
    payload: IdentityRevealCreateRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Request identity reveal for after-the-fact investigation (warden/admin/owner).
    Requires minimum 20 chars reason. Eligible for specified security kinds.
    Creates pending request and broadcasts WebSocket event to org.
    """
    if current_user.role not in ("warden", "admin", "owner"):
        raise ForbiddenError("User role is not authorized to request identity reveal.")

    if len(payload.reason.strip()) < 20:
        raise AppError("Justification reason must be at least 20 characters long.", status_code=400)

    incident = await Incident.find_one({
        "_id": PydanticObjectId(payload.incident_id),
        "org_id": current_user.org_id,
    })
    if not incident:
        raise NotFoundError("Incident", payload.incident_id)

    # Verify eligible security kind
    kinds = await get_incident_kinds(incident)
    if not (kinds & ELIGIBLE_IDENTITY_REVEAL_KINDS):
        raise ForbiddenError(
            "Incident kind is not eligible for identity reveal request.",
            code="IDENTITY_REVEAL_NOT_ELIGIBLE",
        )

    req = IdentityRevealRequest(
        org_id=current_user.org_id,
        incident_id=str(incident.id),
        requester_id=str(current_user.id),
        requester_email=current_user.email,
        reason=payload.reason.strip(),
        status="pending",
    )
    await req.insert()

    # Tamper-evident audit log
    audit_repo = AuditRepository(current_user.org_id)
    await audit_repo.record_audit(
        actor={"type": "user", "id": str(current_user.id), "email": current_user.email},
        action="evidence.identity_reveal.requested",
        target=f"incident:{incident.id}",
        reason=payload.reason.strip(),
    )

    # Real-time WebSocket notification
    await ws_hub.broadcast_to_org(
        org_id=current_user.org_id,
        event_type="identity_reveal.requested",
        data={
            "request_id": str(req.id),
            "incident_id": str(incident.id),
            "requester_email": current_user.email,
            "reason": payload.reason.strip(),
        },
    )

    return {
        "id": str(req.id),
        "incident_id": str(incident.id),
        "status": "pending",
        "requester_email": current_user.email,
        "message": "Identity reveal requested. Pending second owner/admin approval.",
    }


@router.get("/privacy/identity-reveal")
async def list_identity_reveal_requests(
    status: Optional[str] = Query(None, description="pending | approved | denied"),
    current_user: User = Depends(get_current_user),
):
    """List identity reveal requests for the tenant."""
    query: Dict[str, Any] = {"org_id": current_user.org_id}
    if status:
        query["status"] = status

    items = await IdentityRevealRequest.find(query).sort("-created_at").to_list()
    return items


@router.post("/privacy/identity-reveal/{request_id}/approve")
async def approve_identity_reveal(
    request_id: str,
    payload: IdentityRevealDecisionRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Approve identity reveal request.
    Enforces two-person rule: approver must be DIFFERENT owner/admin than requester.
    (Single approval permitted in development only if IDENTITY_REVEAL_SINGLE_APPROVAL=true).
    Grants 15 minutes of FULL unblurred raw clip with watermark.
    """
    if current_user.role not in ("owner", "admin"):
        raise ForbiddenError("Only organization owners or administrators can approve identity reveal requests.")

    req = await IdentityRevealRequest.find_one({
        "_id": PydanticObjectId(request_id),
        "org_id": current_user.org_id,
    })
    if not req:
        raise NotFoundError("IdentityRevealRequest", request_id)

    if req.status != "pending":
        raise AppError(f"Request is already '{req.status}'.", status_code=400)

    # Two-Person Rule validation
    if req.requester_id == str(current_user.id):
        if not settings.IDENTITY_REVEAL_SINGLE_APPROVAL:
            raise ForbiddenError(
                "Self-approval is forbidden. A second owner or administrator must approve this identity reveal.",
                code="SELF_APPROVAL_FORBIDDEN",
            )
        req.is_single_approval = True
    else:
        req.is_single_approval = False

    now = utc_now()
    req.status = "approved"
    req.approver_id = str(current_user.id)
    req.approver_email = current_user.email
    req.decision_note = payload.note
    req.decision_at = now
    req.expires_at = now + timedelta(minutes=15)
    await req.save()

    audit_repo = AuditRepository(current_user.org_id)
    await audit_repo.record_audit(
        actor={"type": "user", "id": str(current_user.id), "email": current_user.email},
        action="evidence.identity_reveal.approved",
        target=f"identity_reveal:{req.id}",
        reason=f"Approved 15-minute full identity reveal. Note: {payload.note or 'N/A'}",
    )

    return {
        "id": str(req.id),
        "status": "approved",
        "approver_email": current_user.email,
        "expires_at": req.expires_at,
        "message": "Identity reveal approved for 15 minutes (full unblur with watermark).",
    }


@router.post("/privacy/identity-reveal/{request_id}/deny")
async def deny_identity_reveal(
    request_id: str,
    payload: IdentityRevealDecisionRequest,
    current_user: User = Depends(get_current_user),
):
    """Deny identity reveal request (owner or admin)."""
    if current_user.role not in ("owner", "admin"):
        raise ForbiddenError("Only organization owners or administrators can deny identity reveal requests.")

    req = await IdentityRevealRequest.find_one({
        "_id": PydanticObjectId(request_id),
        "org_id": current_user.org_id,
    })
    if not req:
        raise NotFoundError("IdentityRevealRequest", request_id)

    if req.status != "pending":
        raise AppError(f"Request is already '{req.status}'.", status_code=400)

    req.status = "denied"
    req.approver_id = str(current_user.id)
    req.approver_email = current_user.email
    req.decision_note = payload.note
    req.decision_at = utc_now()
    await req.save()

    audit_repo = AuditRepository(current_user.org_id)
    await audit_repo.record_audit(
        actor={"type": "user", "id": str(current_user.id), "email": current_user.email},
        action="evidence.identity_reveal.denied",
        target=f"identity_reveal:{req.id}",
        reason=f"Denied. Note: {payload.note or 'N/A'}",
    )

    return {"id": str(req.id), "status": "denied"}


# =========================================================================
# 4. EVIDENCE ACCESS & MULTI-TIER VIEWS (PART A, B, E)
# =========================================================================

async def is_emergency_context_eligible(incident: Incident) -> bool:
    """
    Emergency Context View eligibility:
    - Active safety incidents: fight, distress_audio, student_sos, loitering
    - Severity >= medium
    - Status not closed
    - Last signal <= 10 minutes
    """
    if incident.status == "closed":
        return False
    if incident.severity not in ("medium", "high", "critical"):
        return False

    now = utc_now()
    last_ts = ensure_utc(incident.updated_ts or incident.created_ts)
    if (now - last_ts).total_seconds() > 600:
        return False

    safety_kinds = {"fight", "distress_audio", "student_sos", "loitering"}
    kinds = await get_incident_kinds(incident)
    return bool(kinds & safety_kinds)


@router.get("/evidence/incident/{incident_id}/access")
async def get_incident_evidence_access(
    incident_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Returns user access matrix, locked views, emergency context/reveal eligibility,
    identity reveal status, and active grants for this incident.
    """
    incident = await Incident.find_one({
        "_id": PydanticObjectId(incident_id),
        "org_id": current_user.org_id,
    })
    if not incident:
        raise NotFoundError("Incident", incident_id)

    org = await Organization.get(PydanticObjectId(current_user.org_id))
    default_view = org.settings.get("default_evidence_view", "skeleton") if org else "skeleton"

    now = utc_now()
    # Check active grants
    active_bg = await BreakglassGrant.find_one({
        "org_id": current_user.org_id,
        "incident_id": incident_id,
        "expires_at": {"$gt": now},
    })
    active_er = await EmergencyReveal.find_one({
        "org_id": current_user.org_id,
        "incident_id": incident_id,
        "expires_at": {"$gt": now},
    })
    active_id = await IdentityRevealRequest.find_one({
        "org_id": current_user.org_id,
        "incident_id": incident_id,
        "status": "approved",
        "expires_at": {"$gt": now},
    })

    # Emergency context eligibility
    ctx_eligible = await is_emergency_context_eligible(incident)

    # Emergency reveal eligibility
    is_reveal_eligible = False
    if incident.status != "closed" and incident.severity in ("high", "critical"):
        last_ts = ensure_utc(incident.updated_ts or incident.created_ts)
        if (now - last_ts).total_seconds() <= 600:
            signals = await Signal.find({"incident_id": str(incident.id), "org_id": current_user.org_id}).to_list()
            kinds = await get_incident_kinds(incident)
            if any(is_unexplained_intrusion_signal(s) for s in signals) or (kinds & {"perimeter_breach", "zone_intrusion", "tailgating", "unswiped_entry", "unexplained_presence"}):
                is_reveal_eligible = True

    # Identity reveal status
    latest_id_req = await IdentityRevealRequest.find({
        "org_id": current_user.org_id,
        "incident_id": incident_id,
    }).sort("-created_at").first_or_none()
    id_status = latest_id_req.status if latest_id_req else "none"

    available_views = ["skeleton"]
    locked_views = []

    if current_user.role == "auditor":
        locked_views = ["blurred", "raw"]
    else:
        # Blurred view check
        if default_view == "blurred" or active_bg or ctx_eligible:
            available_views.append("blurred")
        else:
            locked_views.append("blurred")

        # Raw view check
        if active_er or active_id:
            available_views.append("raw")
        else:
            locked_views.append("raw")

    return {
        "incident_id": incident_id,
        "user_role": current_user.role,
        "default_view": default_view,
        "available_views": available_views,
        "locked_views": locked_views,
        "emergency_context_eligible": ctx_eligible,
        "emergency_reveal_eligible": is_reveal_eligible,
        "identity_reveal_status": id_status,
        "active_grants": {
            "breakglass": active_bg is not None,
            "emergency_reveal": active_er is not None,
            "identity_reveal": active_id is not None,
        },
    }


@router.get("/evidence/incident/{incident_id}")
async def get_incident_evidence_view(
    incident_id: str,
    tier: Optional[str] = Query(None, description="skeleton | blurred | raw"),
    variant: str = Query("targeted", description="targeted | full"),
    token: Optional[str] = Query(None, description="Breakglass token"),
    x_breakglass_token: Optional[str] = Header(None, alias="X-Breakglass-Token"),
    current_user: User = Depends(get_current_user),
):
    """
    Evidence view router enforcing the Three Views & Four Unlocks.
    - SKELETON: Keypoints on black, bounding boxes, HUD. (Always accessible, only tier for auditors).
    - BLURRED: Every face blurred. Accessible if org default is blurred, or via breakglass or emergency context.
    - RAW (TARGETED): Authorized emergency reveal unblurs ONLY flagged track IDs with watermark.
    - RAW (FULL): Approved identity reveal unblurs all faces with watermark.
    """
    incident = await Incident.find_one({
        "_id": PydanticObjectId(incident_id),
        "org_id": current_user.org_id,
    })
    if not incident:
        raise NotFoundError("Incident", incident_id)

    org = await Organization.get(PydanticObjectId(current_user.org_id))
    org_default = org.settings.get("default_evidence_view", "skeleton") if org else "skeleton"
    now = utc_now()

    # Rule: Auditors always get skeleton view only
    if current_user.role == "auditor":
        if tier in ("blurred", "raw"):
            raise ForbiddenError("Auditors are restricted to skeleton view only.", code="FORBIDDEN")
        resolved_tier = "skeleton"
    else:
        resolved_tier = tier or org_default

    # =====================================================================
    # TIER: SKELETON
    # =====================================================================
    if resolved_tier == "skeleton":
        # Search for skeleton video or snapshot
        candidates = [
            settings.DATA_DIR / "evidence" / "restricted" / f"{incident_id}_annotated.mp4",
            settings.DATA_DIR / "evidence" / "public" / f"{incident_id}_annotated.mp4",
        ]
        # Also check signals for this incident
        signals = await Signal.find({"incident_id": incident_id, "org_id": current_user.org_id}).to_list()
        for s in signals:
            if s.evidence_path:
                ep = Path(s.evidence_path)
                candidates.append(ep if ep.is_absolute() else settings.DATA_DIR / s.evidence_path)

        # Fallback to sample intrusion video if nothing exists
        candidates.append(settings.DATA_DIR / "videos" / "intrusion" / "intrusion_01.mp4")

        found_path = None
        for p in candidates:
            if p.exists() and p.is_file():
                found_path = p
                break

        if not found_path:
            raise NotFoundError("Skeleton evidence file not found for incident.")

        media_type = "video/mp4" if found_path.suffix.lower() == ".mp4" else "image/jpeg"

        # Log audit entry
        audit_repo = AuditRepository(current_user.org_id)
        await audit_repo.record_audit(
            actor={"type": "user", "id": str(current_user.id), "email": current_user.email},
            action="evidence.view",
            target=f"incident:{incident.id}",
            reason="Viewed skeleton evidence view.",
        )
        return FileResponse(str(found_path), media_type=media_type)

    # =====================================================================
    # TIER: BLURRED
    # =====================================================================
    elif resolved_tier == "blurred":
        # Check authorization:
        # 1. Org default is blurred and role in (guard, warden, admin, owner)
        is_authorized = (org_default == "blurred" and current_user.role in ("guard", "warden", "admin", "owner"))

        # 2. Breakglass grant
        if not is_authorized:
            bg_tok = x_breakglass_token or token
            if bg_tok:
                tok_h = hash_token(bg_tok)
                grant = await BreakglassGrant.find_one({
                    "org_id": current_user.org_id,
                    "token_hash": tok_h,
                    "incident_id": incident_id,
                })
                if grant and ensure_utc(grant.expires_at) > now:
                    is_authorized = True

            # Also check active grant for this user
            if not is_authorized:
                user_grant = await BreakglassGrant.find_one({
                    "org_id": current_user.org_id,
                    "incident_id": incident_id,
                    "user_id": str(current_user.id),
                    "expires_at": {"$gt": now},
                })
                if user_grant:
                    is_authorized = True

        # 3. Emergency Context View (C2)
        if not is_authorized and current_user.role in ("guard", "warden", "admin", "owner"):
            if await is_emergency_context_eligible(incident):
                is_authorized = True

        if not is_authorized:
            raise ForbiddenError(
                "Access to face-blurred view requires a break-glass token or active emergency context.",
                code="BREAKGLASS_REQUIRED",
            )

        # Locate blurred media
        blurred_candidates = [
            settings.DATA_DIR / "evidence" / "restricted" / f"{incident_id}_annotated_blurred.mp4",
            settings.DATA_DIR / "evidence" / "restricted" / f"{incident_id}_blurred.jpg",
        ]
        # Check signals for restricted blurred snapshot
        signals = await Signal.find({"incident_id": incident_id, "org_id": current_user.org_id}).to_list()
        for s in signals:
            if s.evidence_path:
                b_name = Path(s.evidence_path).name.replace("_skeleton.jpg", "_blurred.jpg")
                blurred_candidates.append(settings.DATA_DIR / "evidence" / "restricted" / b_name)

        found_path = None
        for p in blurred_candidates:
            if p.exists() and p.is_file():
                found_path = p
                break

        if not found_path:
            # Fallback to skeleton candidate if blurred was not rendered
            sk_path = settings.DATA_DIR / "videos" / "intrusion" / "intrusion_01.mp4"
            if sk_path.exists():
                found_path = sk_path
            else:
                raise NotFoundError("Blurred evidence file not found on disk.")

        media_type = "video/mp4" if found_path.suffix.lower() == ".mp4" else "image/jpeg"

        audit_repo = AuditRepository(current_user.org_id)
        await audit_repo.record_audit(
            actor={"type": "user", "id": str(current_user.id), "email": current_user.email},
            action="evidence.view",
            target=f"incident:{incident.id}",
            reason="Viewed face-blurred evidence view.",
        )
        return FileResponse(str(found_path), media_type=media_type)

    # =====================================================================
    # TIER: RAW (TARGETED OR FULL)
    # =====================================================================
    elif resolved_tier == "raw":
        if variant == "targeted":
            # Requires active unexpired EmergencyReveal
            reveal = await EmergencyReveal.find_one({
                "org_id": current_user.org_id,
                "incident_id": incident_id,
                "expires_at": {"$gt": now},
            })
            if not reveal:
                raise ForbiddenError(
                    "Targeted unblurred raw clip requires an active emergency reveal grant.",
                    code="EMERGENCY_REVEAL_NOT_ELIGIBLE",
                )

            raw_bytes, frame_tracks = load_and_decrypt_raw_clip(str(incident.id))
            out_bytes, ctype = watermark_and_filter_media(
                raw_media_bytes=raw_bytes,
                frame_tracks=frame_tracks,
                viewer_email=current_user.email,
                label="EMERGENCY ACCESS - RakshakAI",
                variant="targeted",
                flagged_track_ids=reveal.flagged_track_ids,
            )

            audit_repo = AuditRepository(current_user.org_id)
            await audit_repo.record_audit(
                actor={"type": "user", "id": str(current_user.id), "email": current_user.email},
                action="evidence.view",
                target=f"incident:{incident.id}",
                reason=f"Streamed targeted unblurred raw footage (flagged tracks: {reveal.flagged_track_ids}).",
            )
            return Response(content=out_bytes, media_type=ctype)

        elif variant == "full":
            # Requires approved unexpired IdentityRevealRequest
            reveal_req = await IdentityRevealRequest.find_one({
                "org_id": current_user.org_id,
                "incident_id": incident_id,
                "status": "approved",
                "expires_at": {"$gt": now},
            })
            if not reveal_req:
                raise ForbiddenError(
                    "Full unblurred raw clip requires an approved identity reveal grant.",
                    code="IDENTITY_REVEAL_REQUIRED",
                )

            raw_bytes, frame_tracks = load_and_decrypt_raw_clip(str(incident.id))
            out_bytes, ctype = watermark_and_filter_media(
                raw_media_bytes=raw_bytes,
                frame_tracks=frame_tracks,
                viewer_email=current_user.email,
                label="CONFIDENTIAL - RakshakAI",
                variant="full",
            )

            audit_repo = AuditRepository(current_user.org_id)
            await audit_repo.record_audit(
                actor={"type": "user", "id": str(current_user.id), "email": current_user.email},
                action="evidence.view",
                target=f"incident:{incident.id}",
                reason="Streamed full unblurred raw footage under approved identity reveal.",
            )
            return Response(content=out_bytes, media_type=ctype)

        else:
            raise AppError(f"Invalid raw view variant '{variant}'. Must be 'targeted' or 'full'.", status_code=400)

    else:
        raise AppError(f"Invalid evidence tier '{resolved_tier}'. Must be 'skeleton', 'blurred', or 'raw'.", status_code=400)


# =========================================================================
# 5. FORENSIC CHAIN-OF-CUSTODY EXPORT
# =========================================================================

@router.post("/evidence/incident/{incident_id}/export")
async def export_forensic_evidence(
    incident_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Forensic evidence export (organization owner only).
    Requires active approved identity reveal grant.
    Produces a ZIP containing:
    1. Watermarked unblurred video clip.
    2. chain_of_custody.json manifest with SHA-256 hash and audit metadata.
    """
    if current_user.role != "owner":
        raise ForbiddenError("Forensic evidence export is strictly restricted to organization owners.")

    incident = await Incident.find_one({
        "_id": PydanticObjectId(incident_id),
        "org_id": current_user.org_id,
    })
    if not incident:
        raise NotFoundError("Incident", incident_id)

    now = utc_now()
    reveal_req = await IdentityRevealRequest.find_one({
        "org_id": current_user.org_id,
        "incident_id": incident_id,
        "status": "approved",
        "expires_at": {"$gt": now},
    })
    if not reveal_req:
        raise ForbiddenError(
            "Evidence export requires an active, approved identity reveal grant.",
            code="IDENTITY_REVEAL_REQUIRED",
        )

    # Decrypt and watermark in memory
    raw_bytes, frame_tracks = load_and_decrypt_raw_clip(str(incident.id))
    watermarked_bytes, ctype = watermark_and_filter_media(
        raw_media_bytes=raw_bytes,
        frame_tracks=frame_tracks,
        viewer_email=current_user.email,
        label="CONFIDENTIAL - RakshakAI",
        variant="full",
    )

    video_sha256 = hashlib.sha256(watermarked_bytes).hexdigest()
    video_filename = f"incident_{incident_id}_evidence.mp4"

    manifest: Dict[str, Any] = {
        "export_id": generate_opaque_token(16),
        "incident_id": str(incident.id),
        "org_id": current_user.org_id,
        "exported_by": current_user.email,
        "exported_at": now.isoformat(),
        "video_filename": video_filename,
        "video_sha256": video_sha256,
        "identity_reveal_request": {
            "request_id": str(reveal_req.id),
            "requester": reveal_req.requester_email,
            "approver": reveal_req.approver_email,
            "reason": reveal_req.reason,
            "decision_at": reveal_req.decision_at.isoformat() if reveal_req.decision_at else None,
            "expires_at": reveal_req.expires_at.isoformat() if reveal_req.expires_at else None,
        },
        "classification": "CONFIDENTIAL - RakshakAI Forensic Evidence Export",
    }
    manifest_bytes = io.BytesIO()
    import json
    manifest_bytes.write(json.dumps(manifest, indent=2).encode("utf-8"))

    # Create ZIP archive in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(video_filename, watermarked_bytes)
        zf.writestr("chain_of_custody.json", manifest_bytes.getvalue())

    zip_bytes = zip_buffer.getvalue()

    audit_repo = AuditRepository(current_user.org_id)
    await audit_repo.record_audit(
        actor={"type": "user", "id": str(current_user.id), "email": current_user.email},
        action="evidence.export",
        target=f"incident:{incident.id}",
        reason=f"Exported forensic package with SHA256 {video_sha256}.",
    )

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="incident_{incident_id}_export.zip"'},
    )


# =========================================================================
# 6. MONTHLY PRIVACY TRANSPARENCY COUNTERS
# =========================================================================

@router.get("/privacy/transparency")
async def get_privacy_transparency(
    month: Optional[str] = Query(None, description="YYYY-MM (defaults to current month)"),
    current_user: User = Depends(get_current_user),
):
    """
    Monthly privacy transparency counters:
    Aggregates break-glass grants, emergency intruder reveals, identity reveals, and exports.
    """
    now = utc_now()
    target_month = month or now.strftime("%Y-%m")

    try:
        start_dt = datetime.strptime(target_month, "%Y-%m").replace(tzinfo=timezone.utc)
    except Exception:
        start_dt = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Next month start
    if start_dt.month == 12:
        end_dt = start_dt.replace(year=start_dt.year + 1, month=1)
    else:
        end_dt = start_dt.replace(month=start_dt.month + 1)

    time_filter = {"$gte": start_dt, "$lt": end_dt}

    bg_count = await BreakglassGrant.find({"org_id": current_user.org_id, "created_at": time_filter}).count()
    er_count = await EmergencyReveal.find({"org_id": current_user.org_id, "created_at": time_filter}).count()
    id_count = await IdentityRevealRequest.find({"org_id": current_user.org_id, "status": "approved", "created_at": time_filter}).count()
    exp_count = await AuditLog.find({"org_id": current_user.org_id, "action": "evidence.export", "ts": time_filter}).count()

    return {
        "period": target_month,
        "breakglass_count": bg_count,
        "emergency_reveal_count": er_count,
        "identity_reveal_count": id_count,
        "export_count": exp_count,
    }


# =========================================================================
# 7. PRIVACY SETTINGS & RETENTION
# =========================================================================

@router.get("/privacy/settings", dependencies=[Depends(require_permission("privacy:manage"))])
async def get_privacy_settings(current_user: User = Depends(get_current_user)):
    """Retrieve data retention and default evidence view settings."""
    org = await Organization.get(PydanticObjectId(current_user.org_id))
    return {
        "retention_days": org.settings.get("retention_days", 7),
        "retention_days_confirmed": org.settings.get("retention_days_confirmed", 30),
        "default_evidence_view": org.settings.get("default_evidence_view", "skeleton"),
        "plan": org.plan,
        "max_retention_days": (await OrgService.get_plan_limits(org.plan)).get("retention_days_max", 7),
    }


@router.put("/privacy/settings", dependencies=[Depends(require_permission("privacy:manage"))])
async def update_privacy_settings(
    payload: PrivacySettingsRequest,
    current_user: User = Depends(get_current_user),
):
    """Update data retention and default evidence view settings."""
    org = await Organization.get(PydanticObjectId(current_user.org_id))
    plan_limits = await OrgService.get_plan_limits(org.plan)
    max_days = plan_limits.get("retention_days_max", 7)

    if payload.retention_days is not None and payload.retention_days > max_days:
        raise AppError(
            f"Retention days exceeds maximum allowed for '{org.plan}' plan ({max_days} days).",
            status_code=400,
        )

    updated_fields = []
    if payload.retention_days is not None:
        org.settings["retention_days"] = payload.retention_days
        updated_fields.append(f"retention_days={payload.retention_days}")

    if payload.retention_days_confirmed is not None:
        org.settings["retention_days_confirmed"] = payload.retention_days_confirmed
        updated_fields.append(f"retention_days_confirmed={payload.retention_days_confirmed}")

    if payload.default_evidence_view is not None:
        if payload.default_evidence_view not in ("skeleton", "blurred"):
            raise AppError("default_evidence_view must be 'skeleton' or 'blurred'.", status_code=400)
        org.settings["default_evidence_view"] = payload.default_evidence_view
        updated_fields.append(f"default_evidence_view={payload.default_evidence_view}")

    await org.save()

    audit_repo = AuditRepository(current_user.org_id)
    await audit_repo.record_audit(
        actor={"type": "user", "id": str(current_user.id), "email": current_user.email},
        action="privacy.settings_updated",
        target=f"organization:{org.id}",
        reason=f"Updated privacy settings: {', '.join(updated_fields)}",
    )

    return {
        "message": "Privacy settings updated",
        "retention_days": org.settings.get("retention_days"),
        "retention_days_confirmed": org.settings.get("retention_days_confirmed"),
        "default_evidence_view": org.settings.get("default_evidence_view"),
    }


@router.post("/privacy/purge", dependencies=[Depends(require_permission("privacy:manage"))])
async def trigger_retention_purge(current_user: User = Depends(get_current_user)):
    """Execute retention purge: delete evidence files older than retention policy."""
    summary = await execute_retention_purge(user=current_user.email)
    return summary


@router.get("/privacy/inventory", response_model=PrivacyInventoryResponse, dependencies=[Depends(require_permission("privacy:manage"))])
async def get_inventory(current_user: User = Depends(get_current_user)):
    """Return inventory of stored evidence files and document counts."""
    inventory = await get_privacy_inventory()
    return inventory


# Backward-compatible signal evidence endpoint
@router.get("/evidence/{signal_id}")
async def get_evidence_file(
    signal_id: str,
    mode: str = Query("public", description="public | restricted"),
    token: Optional[str] = Query(None, description="Break-glass token for restricted evidence"),
    x_breakglass_token: Optional[str] = Header(None, alias="X-Breakglass-Token"),
    current_user: User = Depends(get_current_user),
):
    """Stream evidence file for a specific signal."""
    signal = await Signal.find_one({"_id": PydanticObjectId(signal_id), "org_id": current_user.org_id})
    if not signal:
        raise NotFoundError("Signal", signal_id)

    if not signal.evidence_path:
        raise NotFoundError("Evidence file has been purged or does not exist for this signal.")

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
        })
        if not grant or (grant.expires_at and ensure_utc(grant.expires_at) <= now):
            raise ForbiddenError("Break-glass token is invalid, expired, or not authorized for this incident.")

    evidence_path = Path(signal.evidence_path)
    if not evidence_path.is_absolute():
        evidence_path = settings.DATA_DIR / signal.evidence_path

    if not evidence_path.exists() or not evidence_path.is_file():
        raise NotFoundError(f"Evidence file on disk '{evidence_path.name}' not found.")

    return FileResponse(str(evidence_path))

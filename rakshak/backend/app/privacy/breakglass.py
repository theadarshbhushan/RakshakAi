"""
Break-glass emergency privacy override protocol for RakshakAI.
Admins can request emergency access to restricted evidence for an incident.
The issued token is scoped to that specific incident, valid for 10 minutes,
stored only as an irreversible SHA-256 hash in the database, and audited.
"""
import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Tuple, Optional
from app.models.privacy import BreakglassGrant
from app.models.user import utc_now
from app.repositories.repos import AuditRepository


async def issue_breakglass_token(org_id: str, incident_id: str, user_id: str, user_email: str, reason: str) -> Tuple[str, datetime]:
    """
    Issue a new break-glass token valid for 10 minutes, scoped to the incident.
    Returns (raw_token, expires_at). Only the hash is saved to the database.
    """
    if not reason or len(reason.strip()) < 10:
        raise ValueError("Break-glass justification reason must be at least 10 characters long.")

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    expires_at = utc_now() + timedelta(minutes=10)

    token_doc = BreakglassGrant(
        org_id=org_id,
        incident_id=incident_id,
        user_id=user_id,
        reason=reason.strip(),
        token_hash=token_hash,
        expires_at=expires_at,
    )
    await token_doc.insert()

    audit_repo = AuditRepository(org_id)
    await audit_repo.record_audit(
        actor={"type": "user", "id": user_id, "email": user_email},
        action="evidence.breakglass",
        target=f"incident:{incident_id}",
        reason=reason.strip(),
    )

    return raw_token, expires_at


async def verify_breakglass_token(org_id: str, raw_token: str, incident_id: str) -> bool:
    """
    Verify whether the provided token is valid, active, and scoped to the incident within this tenant.
    """
    if not raw_token or not incident_id:
        return False

    token_hash = hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()
    now = utc_now()

    token_doc = await BreakglassGrant.find_one({
        "org_id": org_id,
        "token_hash": token_hash,
        "incident_id": incident_id,
        "expires_at": {"$gt": now},
    })

    return token_doc is not None

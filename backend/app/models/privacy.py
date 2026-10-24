"""
Privacy and Evidence Access Models:
- BreakglassGrant: 10-minute emergency face-blurred view override scoped to incident or job.
- EmergencyReveal: 5-minute instant targeted unblur for unexplained intrusion signals with post-review task.
- IdentityRevealRequest: Two-person approved 15-minute full unblur for after-the-fact investigation.
"""
from datetime import datetime, timezone
from typing import List, Optional

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, IndexModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BreakglassGrant(Document):
    org_id: str
    incident_id: Optional[str] = None
    job_id: Optional[str] = None
    user_id: str
    reason: str
    token_hash: str
    created_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime = Field(..., description="10-minute expiration TTL")

    class Settings:
        name = "breakglass_grants"
        indexes = [
            IndexModel([("token_hash", ASCENDING)]),
            IndexModel([("org_id", ASCENDING), ("incident_id", ASCENDING)]),
            IndexModel([("org_id", ASCENDING), ("job_id", ASCENDING)]),
            IndexModel([("expires_at", ASCENDING)], expireAfterSeconds=0),
        ]


class EmergencyReveal(Document):
    org_id: str
    incident_id: str
    user_id: str
    user_email: str
    reason: str
    flagged_track_ids: List[int] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime = Field(..., description="5-minute expiration TTL")
    review_status: str = Field(default="pending", description="pending | justified | not_justified")
    reviewed_by: Optional[str] = None
    review_note: Optional[str] = None
    reviewed_at: Optional[datetime] = None

    class Settings:
        name = "emergency_reveals"
        indexes = [
            IndexModel([("org_id", ASCENDING), ("incident_id", ASCENDING)]),
            IndexModel([("org_id", ASCENDING), ("review_status", ASCENDING)]),
            IndexModel([("expires_at", ASCENDING)], expireAfterSeconds=0),
        ]


class IdentityRevealRequest(Document):
    org_id: str
    incident_id: str
    requester_id: str
    requester_email: str
    reason: str
    status: str = Field(default="pending", description="pending | approved | denied")
    approver_id: Optional[str] = None
    approver_email: Optional[str] = None
    decision_note: Optional[str] = None
    decision_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None  # 15-minute expiration TTL after approval
    is_single_approval: bool = False
    created_at: datetime = Field(default_factory=utc_now)

    class Settings:
        name = "identity_reveal_requests"
        indexes = [
            IndexModel([("org_id", ASCENDING), ("incident_id", ASCENDING)]),
            IndexModel([("org_id", ASCENDING), ("status", ASCENDING)]),
            IndexModel([("expires_at", ASCENDING)], expireAfterSeconds=0),
        ]

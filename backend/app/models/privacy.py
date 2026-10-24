"""
Breakglass grant model for emergency restricted evidence access.
"""
from datetime import datetime, timezone

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, IndexModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BreakglassGrant(Document):
    org_id: str
    incident_id: str
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
            IndexModel([("expires_at", ASCENDING)], expireAfterSeconds=0),
        ]

"""
Cryptographic, tamper-evident, append-only audit log document model.
Each tenant organization maintains an independent, unbroken hash chain.
"""
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from pydantic import Field
from beanie import Document
from pymongo import IndexModel, ASCENDING


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AuditLog(Document):
    org_id: str
    seq: int = Field(..., description="Per-org incrementing sequence number")
    ts: datetime = Field(default_factory=utc_now)
    actor: Dict[str, Any] = Field(..., description="{'type': 'user|api_key|system', 'id': '...', 'email': '...'}")
    action: str = Field(..., description="e.g. auth.login, incident.reviewed, evidence.breakglass")
    target: str
    reason: str
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    request_id: Optional[str] = None
    prev_hash: str
    hash: str

    class Settings:
        name = "audit_log"
        indexes = [
            IndexModel([("org_id", ASCENDING), ("seq", ASCENDING)], unique=True),
            IndexModel([("org_id", ASCENDING), ("ts", ASCENDING)]),
            IndexModel([("org_id", ASCENDING), ("action", ASCENDING)]),
        ]

"""
Signal and AccessEvent document models.
Signal includes TTL index on evidence_expires_at for non-incident suppressed signals.
Raw card_id is never stored; only salted SHA-256 pseudo_id is stored in AccessEvent.
"""
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, DESCENDING, IndexModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Signal(Document):
    org_id: str
    site_id: Optional[str] = None
    ts: datetime = Field(default_factory=utc_now)
    modality: str = Field(..., description="video | audio | access")
    kind: str = Field(..., description="zone_intrusion | fight | line_crossing | tailgating | distress_audio | curfew_violation | restricted_access | loitering | camera_tamper")
    zone_id: str
    camera_id: Optional[str] = None
    score: float = 1.0
    threshold: float = 0.5
    details: Dict[str, Any] = Field(default_factory=dict)
    suppressed: bool = False
    suppress_reason: Optional[str] = None
    evidence_path: Optional[str] = None
    evidence_expires_at: Optional[datetime] = None  # TTL index on evidence_expires_at
    incident_id: Optional[str] = None
    source: str = Field(default="scenario", description="scenario | edge_device")

    class Settings:
        name = "signals"
        indexes = [
            IndexModel([("org_id", ASCENDING), ("zone_id", ASCENDING), ("ts", DESCENDING)]),
            IndexModel([("org_id", ASCENDING), ("incident_id", ASCENDING)]),
            IndexModel([("org_id", ASCENDING), ("suppressed", ASCENDING), ("ts", DESCENDING)]),
            IndexModel([("evidence_expires_at", ASCENDING)], expireAfterSeconds=0),
        ]


class AccessEvent(Document):
    org_id: str
    site_id: Optional[str] = None
    ts: datetime = Field(default_factory=utc_now)
    pseudo_id: str = Field(..., description="Salted SHA-256 first 8 chars")
    role: str
    door_id: str
    zone_id: str
    direction: str = Field(..., description="in | out")
    result: str = Field(..., description="granted | denied")

    class Settings:
        name = "access_events"
        indexes = [
            IndexModel([("org_id", ASCENDING), ("ts", DESCENDING)]),
            IndexModel([("org_id", ASCENDING), ("door_id", ASCENDING), ("ts", DESCENDING)]),
            IndexModel([("org_id", ASCENDING), ("zone_id", ASCENDING), ("ts", DESCENDING)]),
        ]

"""
Incident, Feedback, and ThresholdHistory models.
All tenant-scoped with org_id.
"""
from datetime import datetime, timezone
from typing import List, Optional

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, DESCENDING, IndexModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Incident(Document):
    org_id: str
    site_id: Optional[str] = None
    created_ts: datetime = Field(default_factory=utc_now)
    updated_ts: datetime = Field(default_factory=utc_now)
    zone_id: str
    severity: str = Field(default="low", description="low | medium | high | critical")
    composite_score: float = 0.0
    modalities: List[str] = Field(default_factory=list)
    signal_ids: List[str] = Field(default_factory=list)
    explanation: str = ""
    status: str = Field(default="new", description="new | acknowledged | investigating | confirmed | false_alarm")
    acknowledged_by: Optional[str] = None
    acknowledged_ts: Optional[datetime] = None
    escalated: bool = False
    reviewer: Optional[str] = None
    review_note: Optional[str] = None
    reviewed_ts: Optional[datetime] = None

    class Settings:
        name = "incidents"
        indexes = [
            IndexModel([("org_id", ASCENDING), ("status", ASCENDING), ("severity", ASCENDING), ("created_ts", DESCENDING)]),
            IndexModel([("org_id", ASCENDING), ("zone_id", ASCENDING)]),
        ]


class Feedback(Document):
    org_id: str
    incident_id: str
    user: str
    label: str = Field(..., description="confirmed | false_alarm | investigating")
    note: Optional[str] = None
    ts: datetime = Field(default_factory=utc_now)

    class Settings:
        name = "feedback"
        indexes = [
            IndexModel([("org_id", ASCENDING), ("incident_id", ASCENDING), ("ts", DESCENDING)]),
        ]


class ThresholdHistory(Document):
    org_id: str
    zone_id: str
    detector: str
    old_value: float
    new_value: float
    reason: str
    ts: datetime = Field(default_factory=utc_now)
    reverted: bool = False
    changed_by: Optional[str] = None

    class Settings:
        name = "threshold_history"
        indexes = [
            IndexModel([("org_id", ASCENDING), ("zone_id", ASCENDING), ("detector", ASCENDING)]),
        ]

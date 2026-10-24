"""
Organization and Site document models.
Organization is the root multi-tenant entity.
"""
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, IndexModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Organization(Document):
    name: str = Field(..., description="Organization display name")
    slug: str = Field(..., description="Unique organization slug")
    plan: str = Field(default="free", description="free | pro | enterprise")
    created_at: datetime = Field(default_factory=utc_now)
    settings: Dict[str, Any] = Field(
        default_factory=lambda: {
            "retention_days": 7,
            "fusion_window_s": 30,
            "sla_ack_seconds": 120,
            "context_ratio": 0.8,
            "timezone": "Asia/Kolkata",
        }
    )

    class Settings:
        name = "organizations"
        indexes = [
            IndexModel([("slug", ASCENDING)], unique=True),
        ]


class Site(Document):
    org_id: str = Field(..., description="Parent organization ID")
    name: str = Field(..., description="Site or campus building name")
    address: Optional[str] = None
    timezone: str = Field(default="Asia/Kolkata")
    created_at: datetime = Field(default_factory=utc_now)

    class Settings:
        name = "sites"
        indexes = [
            IndexModel([("org_id", ASCENDING), ("name", ASCENDING)]),
        ]

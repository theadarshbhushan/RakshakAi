"""
Rule document model with versioning per tenant organization.
"""
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from pydantic import Field
from beanie import Document
from pymongo import IndexModel, ASCENDING, DESCENDING


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RuleDocument(Document):
    org_id: str
    version: int = Field(default=1)
    curfew: Dict[str, Any] = Field(default_factory=dict)
    zones: Dict[str, Any] = Field(default_factory=dict)
    tailgating: Dict[str, Any] = Field(default_factory=dict)
    fusion: Dict[str, Any] = Field(default_factory=dict)
    weights: Dict[str, Any] = Field(default_factory=dict)
    updated_by: str = Field(default="system")
    updated_at: datetime = Field(default_factory=utc_now)
    is_active: bool = Field(default=True)

    class Settings:
        name = "rules"
        indexes = [
            IndexModel([("org_id", ASCENDING), ("is_active", ASCENDING)]),
            IndexModel([("org_id", ASCENDING), ("version", DESCENDING)]),
        ]

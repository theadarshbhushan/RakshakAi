"""
Zone and Camera document models.
All tenant-scoped with org_id.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, IndexModel


import secrets

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def generate_sos_token() -> str:
    return secrets.token_urlsafe(16)


class Zone(Document):
    org_id: str
    site_id: str
    zone_id: str = Field(..., description="Unique zone identifier within organization")
    name: str
    type: str = Field(..., description="common | corridor | entry | restricted")
    polygons: Dict[str, Any] = Field(default_factory=dict, description="Normalised 0-1 points per camera")
    allowed_roles: List[str] = Field(default_factory=list)
    adjacent_zone_ids: List[str] = Field(default_factory=list)
    map_coords: Dict[str, Any] = Field(default_factory=dict)
    sos_token: Optional[str] = Field(default_factory=generate_sos_token, description="Random rotatable token for student SOS QR code")
    is_blind_spot: bool = Field(default=False, description="True if camera in zone is tampered or offline")
    blind_spot_reason: Optional[str] = Field(default=None, description="Reason zone is a blind spot")
    blind_spot_adjustments: Optional[Dict[str, Any]] = Field(default=None, description="Active blind spot threshold adjustments")
    created_at: datetime = Field(default_factory=utc_now)

    class Settings:
        name = "zones"
        indexes = [
            IndexModel([("org_id", ASCENDING), ("zone_id", ASCENDING)], unique=True),
            IndexModel([("org_id", ASCENDING), ("site_id", ASCENDING)]),
            IndexModel([("sos_token", ASCENDING)], sparse=True),
        ]


class Camera(Document):
    org_id: str
    site_id: str
    camera_id: str = Field(..., description="Unique camera identifier within organization")
    name: str
    zone_id: str
    source_path: str
    door_line: Optional[Dict[str, Any]] = None  # e.g. {"p1": [0.2, 0.5], "p2": [0.8, 0.5]}
    status: str = Field(default="online")
    health_status: str = Field(default="ok", description="ok | degraded | tampered | offline")
    health_reason: Optional[str] = Field(default=None, description="dark | blur | moved | no frames")
    last_frame_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utc_now)

    class Settings:
        name = "cameras"
        indexes = [
            IndexModel([("org_id", ASCENDING), ("camera_id", ASCENDING)], unique=True),
            IndexModel([("org_id", ASCENDING), ("zone_id", ASCENDING)]),
            IndexModel([("org_id", ASCENDING), ("site_id", ASCENDING)]),
            IndexModel([("org_id", ASCENDING), ("health_status", ASCENDING)]),
        ]

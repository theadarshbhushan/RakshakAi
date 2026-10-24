"""
Pydantic schemas for Organizations, Sites, Zones, Cameras, Invitations, and API Keys.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, EmailStr, Field


# Organization
class OrgResponse(BaseModel):
    id: str
    name: str
    slug: str
    plan: str
    created_at: datetime
    settings: Dict[str, Any]


class OrgPlanUpdateRequest(BaseModel):
    plan: str = Field(..., description="free | pro | enterprise")


# Site
class SiteCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    address: Optional[str] = None
    timezone: str = "Asia/Kolkata"


class SiteResponse(BaseModel):
    id: str
    org_id: str
    name: str
    address: Optional[str] = None
    timezone: str
    created_at: datetime


# Zone
class ZoneCreateRequest(BaseModel):
    site_id: str
    zone_id: str
    name: str
    type: str = Field(..., description="common | corridor | entry | restricted")
    polygons: Dict[str, Any] = Field(default_factory=dict)
    allowed_roles: List[str] = Field(default_factory=list)
    adjacent_zone_ids: List[str] = Field(default_factory=list)
    map_coords: Dict[str, Any] = Field(default_factory=dict)


class ZoneResponse(BaseModel):
    id: str
    org_id: str
    site_id: str
    zone_id: str
    name: str
    type: str
    polygons: Dict[str, Any]
    allowed_roles: List[str]
    adjacent_zone_ids: List[str]
    map_coords: Dict[str, Any]
    sos_token: Optional[str] = None
    is_blind_spot: bool = False
    blind_spot_reason: Optional[str] = None
    created_at: datetime


# Camera
class CameraCreateRequest(BaseModel):
    site_id: str
    camera_id: str
    name: str
    zone_id: str
    source_path: str
    door_line: Optional[Dict[str, Any]] = None


class CameraResponse(BaseModel):
    id: str
    org_id: str
    site_id: str
    camera_id: str
    name: str
    zone_id: str
    source_path: str
    door_line: Optional[Dict[str, Any]] = None
    status: str
    health_status: str = "ok"
    health_reason: Optional[str] = None
    last_frame_at: Optional[datetime] = None
    created_at: datetime


# Invitation
class InvitationCreateRequest(BaseModel):
    email: EmailStr
    role: str = Field(..., description="admin | warden | guard | auditor")


class InvitationAcceptRequest(BaseModel):
    token: str
    full_name: str
    password: str = Field(..., min_length=10)


class InvitationResponse(BaseModel):
    id: str
    org_id: str
    email: str
    role: str
    created_at: datetime
    expires_at: datetime
    accepted_at: Optional[datetime] = None


# API Key
class ApiKeyCreateRequest(BaseModel):
    name: str
    scopes: List[str] = Field(default_factory=lambda: ["signals:write"])
    site_id: Optional[str] = None


class ApiKeyCreateResponse(BaseModel):
    id: str
    name: str
    prefix: str
    key: str = Field(..., description="Raw full key returned ONCE upon creation")
    scopes: List[str]
    site_id: Optional[str] = None
    created_at: datetime


class ApiKeyResponse(BaseModel):
    id: str
    name: str
    prefix: str
    scopes: List[str]
    site_id: Optional[str] = None
    created_at: datetime
    last_used_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None

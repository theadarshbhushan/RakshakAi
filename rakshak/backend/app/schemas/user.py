"""
Pydantic schemas for User Management and Me profile.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class UserResponse(BaseModel):
    id: str
    org_id: str
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None


class UserUpdateRequest(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None


class MeResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    permissions: List[str]
    org_id: str
    org_name: str
    org_slug: str
    plan: str
    settings: Dict[str, Any]

"""
User, RefreshSession, Invitation, PasswordResetToken, and ApiKey models.
All tenant-scoped with indexed org_id.
"""
from datetime import datetime, timezone
from typing import List, Optional
from pydantic import Field
from beanie import Document
from pymongo import IndexModel, ASCENDING, DESCENDING


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Document):
    org_id: str = Field(..., description="Parent organization ID")
    email: str = Field(..., description="Unique email address (lowercase)")
    full_name: str
    password_hash: str
    role: str = Field(..., description="owner | admin | warden | guard | auditor")
    is_active: bool = Field(default=True)
    token_version: int = Field(default=1, description="Incremented on logout-all to invalidate JWTs")
    failed_login_count: int = Field(default=0)
    locked_until: Optional[datetime] = None
    last_login_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utc_now)
    deleted_at: Optional[datetime] = None

    class Settings:
        name = "users"
        indexes = [
            IndexModel([("email", ASCENDING)], unique=True),
            IndexModel([("org_id", ASCENDING), ("role", ASCENDING)]),
            IndexModel([("org_id", ASCENDING), ("is_active", ASCENDING)]),
        ]


class RefreshSession(Document):
    org_id: str
    user_id: str
    family_id: str = Field(..., description="Token rotation family identifier")
    token_hash: str = Field(..., description="SHA-256 hash of refresh token")
    user_agent: Optional[str] = None
    ip: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    last_used_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime = Field(..., description="Session expiration timestamp (TTL)")
    revoked_at: Optional[datetime] = None
    replaced_by: Optional[str] = None

    class Settings:
        name = "refresh_sessions"
        indexes = [
            IndexModel([("token_hash", ASCENDING)]),
            IndexModel([("family_id", ASCENDING)]),
            IndexModel([("user_id", ASCENDING)]),
            IndexModel([("expires_at", ASCENDING)], expireAfterSeconds=0),
        ]


class Invitation(Document):
    org_id: str
    email: str
    role: str
    token_hash: str
    created_by: str
    created_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime = Field(..., description="Invitation expiration (72h TTL)")
    accepted_at: Optional[datetime] = None

    class Settings:
        name = "invitations"
        indexes = [
            IndexModel([("token_hash", ASCENDING)]),
            IndexModel([("org_id", ASCENDING), ("email", ASCENDING)]),
            IndexModel([("expires_at", ASCENDING)], expireAfterSeconds=0),
        ]


class PasswordResetToken(Document):
    org_id: str
    user_id: str
    token_hash: str
    created_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime = Field(..., description="Expiration timestamp (30m TTL)")
    used_at: Optional[datetime] = None

    class Settings:
        name = "password_reset_tokens"
        indexes = [
            IndexModel([("token_hash", ASCENDING)]),
            IndexModel([("expires_at", ASCENDING)], expireAfterSeconds=0),
        ]


class ApiKey(Document):
    org_id: str
    name: str
    prefix: str = Field(..., description="First 8 characters of key for display")
    secret_hash: str = Field(..., description="SHA-256 hash of API key secret")
    scopes: List[str] = Field(default_factory=lambda: ["signals:write"])
    site_id: Optional[str] = None
    created_by: str
    created_at: datetime = Field(default_factory=utc_now)
    last_used_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None

    class Settings:
        name = "api_keys"
        indexes = [
            IndexModel([("prefix", ASCENDING)]),
            IndexModel([("org_id", ASCENDING), ("name", ASCENDING)]),
        ]

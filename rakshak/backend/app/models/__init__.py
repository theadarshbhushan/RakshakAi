"""
All Beanie Document models for RakshakAI multi-tenant platform.
"""
from app.models.organization import Organization, Site
from app.models.user import (
    User,
    RefreshSession,
    Invitation,
    PasswordResetToken,
    ApiKey,
)
from app.models.zone import Zone, Camera
from app.models.signal import Signal, AccessEvent
from app.models.incident import Incident, Feedback, ThresholdHistory
from app.models.rules import RuleDocument
from app.models.privacy import BreakglassGrant
from app.models.audit import AuditLog

ALL_DOCUMENT_MODELS = [
    Organization,
    Site,
    User,
    RefreshSession,
    Invitation,
    PasswordResetToken,
    ApiKey,
    Zone,
    Camera,
    Signal,
    AccessEvent,
    Incident,
    Feedback,
    ThresholdHistory,
    RuleDocument,
    BreakglassGrant,
    AuditLog,
]

__all__ = [
    "Organization",
    "Site",
    "User",
    "RefreshSession",
    "Invitation",
    "PasswordResetToken",
    "ApiKey",
    "Zone",
    "Camera",
    "Signal",
    "AccessEvent",
    "Incident",
    "Feedback",
    "ThresholdHistory",
    "RuleDocument",
    "BreakglassGrant",
    "AuditLog",
    "ALL_DOCUMENT_MODELS",
]
